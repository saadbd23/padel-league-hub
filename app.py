from flask import Flask, render_template, redirect, url_for, request, flash, session, make_response
import os
import secrets
import re
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
from models import (
    db, Team, FreeAgent, Match, Reschedule, Substitute, Player, LeagueSettings,
    LadderTeam, LadderFreeAgent, LadderChallenge, LadderMatch, 
    AmericanoTournament, AmericanoMatch, LadderSettings
)
from utils import (
    generate_round_pairings,
    calculate_match_result,
    invert_score_string,
    normalize_score_string,
    normalize_phone_number,
    normalize_team_name,
    check_swiss_completion,
    generate_playoff_preview,
    get_team_rankings_with_tiebreaker,
    generate_playoff_bracket,
    get_playoff_bracket_data,
)

app = Flask(__name__)

# Ensure .env values override any existing process variables (helps when a stale
# ACCESS_TOKEN is set in the shell/environment)
load_dotenv(override=True)

# Production-ready secret key (CRITICAL: Set SECRET_KEY in environment variables)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

# Database Configuration
# Supports both DATABASE_URL (Replit/Render/Heroku) and DATABASE_URI (legacy)
database_url = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URI")

# Fallback to SQLite only if no database URL is provided
if not database_url:
    database_url = "sqlite:///instance/league.db"
    import logging
    logging.warning("No DATABASE_URL found, using SQLite fallback")

# Fix for Render: postgres:// -> postgresql://
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,  # Verify connections before using
    "pool_recycle": 280,     # Recycle connections after 4.6 minutes (before 5min timeout)
    "pool_size": 5,          # Increase pool size
    "max_overflow": 10,      # Allow more overflow connections
    "pool_timeout": 30,      # Wait up to 30s for a connection from pool
    "connect_args": {
        "connect_timeout": 10,  # 10 second connection timeout
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    } if database_url.startswith("postgresql://") else {}
}

db.init_app(app)

VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "padel_league_2025_verify")


def update_team_stats_from_match(match):
    """Update team and player statistics based on match result"""
    # Check if stats have already been calculated to avoid duplicates
    if match.stats_calculated:
        return

    team_a = Team.query.get(match.team_a_id)
    team_b = Team.query.get(match.team_b_id)

    if not team_a or not team_b:
        return

    # Update team sets and games statistics
    team_a.sets_for += match.sets_a
    team_a.sets_against += match.sets_b
    team_a.games_for += match.games_a
    team_a.games_against += match.games_b

    team_b.sets_for += match.sets_b
    team_b.sets_against += match.sets_a
    team_b.games_for += match.games_b
    team_b.games_against += match.games_a

    # Update team wins/losses/draws and points (3 for win, 1 for draw, 0 for loss)
    if match.winner_id == team_a.id:
        team_a.wins += 1
        team_a.points += 3
        team_b.losses += 1
    elif match.winner_id == team_b.id:
        team_b.wins += 1
        team_b.points += 3
        team_a.losses += 1
    else:
        # Draw
        team_a.draws += 1
        team_a.points += 1
        team_b.draws += 1
        team_b.points += 1

    # Update player statistics for both teams
    update_player_stats_from_match(match, team_a, team_b)

    # CRITICAL: Set flag AFTER updating all stats (team and player) to prevent duplicate processing
    match.stats_calculated = True


def update_player_stats_from_match(match, team_a, team_b):
    """Update individual player statistics based on match result - for ALL players (winners AND losers)"""
    from datetime import datetime

    # CRITICAL: Prevent duplicate stat updates
    if match.stats_calculated:
        return

    # Get or create players for Team A (ALWAYS from team roster)
    players_a = []

    player1_a = Player.query.filter_by(phone=team_a.player1_phone).first()
    if not player1_a:
        # Create player if doesn't exist
        player1_a = Player(
            name=team_a.player1_name,
            phone=team_a.player1_phone,
            email=team_a.player1_email,
            current_team_id=team_a.id,
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        db.session.add(player1_a)
        db.session.flush()

    players_a.append(player1_a)
    # Link to match for future reference
    if not match.team_a_player1_id:
        match.team_a_player1_id = player1_a.id

    if team_a.player2_phone != team_a.player1_phone:
        player2_a = Player.query.filter_by(phone=team_a.player2_phone).first()
        if not player2_a:
            # Create player if doesn't exist
            player2_a = Player(
                name=team_a.player2_name,
                phone=team_a.player2_phone,
                email=team_a.player2_email,
                current_team_id=team_a.id,
                created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
            db.session.add(player2_a)
            db.session.flush()

        players_a.append(player2_a)
        # Link to match for future reference
        if not match.team_a_player2_id:
            match.team_a_player2_id = player2_a.id

    # Get or create players for Team B (ALWAYS from team roster)
    players_b = []

    player1_b = Player.query.filter_by(phone=team_b.player1_phone).first()
    if not player1_b:
        # Create player if doesn't exist
        player1_b = Player(
            name=team_b.player1_name,
            phone=team_b.player1_phone,
            email=team_b.player1_email,
            current_team_id=team_b.id,
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        db.session.add(player1_b)
        db.session.flush()

    players_b.append(player1_b)
    # Link to match for future reference
    if not match.team_b_player1_id:
        match.team_b_player1_id = player1_b.id

    if team_b.player2_phone != team_b.player1_phone:
        player2_b = Player.query.filter_by(phone=team_b.player2_phone).first()
        if not player2_b:
            # Create player if doesn't exist
            player2_b = Player(
                name=team_b.player2_name,
                phone=team_b.player2_phone,
                email=team_b.player2_email,
                current_team_id=team_b.id,
                created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
            db.session.add(player2_b)
            db.session.flush()

        players_b.append(player2_b)
        # Link to match for future reference
        if not match.team_b_player2_id:
            match.team_b_player2_id = player2_b.id

    # Update player stats for Team A (BOTH winners and losers get stats)
    for player in players_a:
        player.matches_played += 1
        player.sets_for += match.sets_a
        player.sets_against += match.sets_b
        player.games_for += match.games_a
        player.games_against += match.games_b

        if match.winner_id == team_a.id:
            player.wins += 1
            player.points += 3
        elif match.winner_id == team_b.id:
            player.losses += 1
            # Losers get 0 points (already default)
        else:
            player.draws += 1
            player.points += 1

    # Update player stats for Team B (BOTH winners and losers get stats)
    for player in players_b:
        player.matches_played += 1
        player.sets_for += match.sets_b
        player.sets_against += match.sets_a
        player.games_for += match.games_b
        player.games_against += match.games_a

        if match.winner_id == team_b.id:
            player.wins += 1
            player.points += 3
        elif match.winner_id == team_a.id:
            player.losses += 1
            # Losers get 0 points (already default)
        else:
            player.draws += 1
            player.points += 1


def recalculate_all_player_stats():
    """Recalculate player stats for all completed league matches"""
    # Reset all player stats to 0
    for player in Player.query.all():
        player.wins = 0
        player.losses = 0
        player.draws = 0
        player.points = 0
        player.matches_played = 0
        player.sets_for = 0
        player.sets_against = 0
        player.games_for = 0
        player.games_against = 0
    
    # Get all completed matches sorted by round and id (to maintain order)
    completed_matches = Match.query.filter(
        Match.status == "completed"
    ).order_by(Match.round, Match.id).all()
    
    # Recalculate stats for each match
    for match in completed_matches:
        team_a = Team.query.get(match.team_a_id)
        team_b = Team.query.get(match.team_b_id)
        
        if team_a and team_b:
            # Use update_player_stats_from_match from app to get proper calculations
            update_player_stats_from_match(match, team_a, team_b)
    
    db.session.commit()
    return len(completed_matches)


def digits_only(s: str) -> str:
    return "".join(ch for ch in (s or "") if ch.isdigit())


def check_admin_auth():
    """Check if user is authenticated as admin"""
    return session.get('admin_authenticated', False)


def require_admin_auth(f):
    """Decorator to require admin authentication for routes"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not check_admin_auth():
            flash("Please log in to access the admin panel", "error")
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function


def get_round_date_range(match):
    """Calculate the date range for a given match, using round_deadline if available"""
    if not match or not match.round:
        return None

    from datetime import datetime, timedelta

    if match.round_deadline:
        # Range is from today (or round start if deadline is far) to deadline
        # The user wants round generation date to deadline
        # Since we don't store generation date explicitly on match, we use 
        # (deadline - 13 days) to allow a ~2 week window if it was set on Jan 4th for Jan 17th
        round_end = match.round_deadline
        round_start = round_end - timedelta(days=13) 
    else:
        # Fallback to legacy hardcoded start date
        # Round 1 starts November 17, 2025 (Monday)
        round_1_start = datetime(2025, 11, 17)
        round_start = round_1_start + timedelta(weeks=match.round - 1)
        round_end = round_start + timedelta(days=6)

    # Format dates
    start_str = round_start.strftime("%b %d")
    end_str = round_end.strftime("%b %d")

    return f"{start_str} - {end_str}"


def get_max_reschedules_per_round():
    """Calculate maximum allowed reschedules per round based on tournament size"""
    total_teams = Team.query.count()
    if total_teams <= 12:
        return max(2, total_teams // 4)  # 25% minimum 2
    elif total_teams <= 20:
        return max(3, total_teams // 3)  # 30% minimum 3
    else:
        return max(4, total_teams // 3)  # 35% minimum 4


def get_pending_reschedules():
    """Get all pending reschedule requests"""
    return Reschedule.query.filter_by(status="pending").all()


def check_deadline_violations():
    """
    Check for matches that missed deadlines and apply automatic walkovers
    TWO types of deadlines:
    1. Regular matches: Sunday 23:59 of the round week
    2. Makeup matches (rescheduled): Wednesday 23:59 of the following week

    Returns dict with regular and makeup walkovers applied
    """
    from datetime import datetime, timedelta

    now = datetime.now()
    walkovers_applied = {
        'regular': [],
        'makeup': []
    }

    # ========================================
    # 1. Check MAKEUP MATCH deadlines (round_deadline + 3 days)
    # ========================================
    pending_reschedules = get_pending_reschedules()

    for reschedule in pending_reschedules:
        # Get the match to determine its round deadline
        match = Match.query.get(reschedule.match_id)
        if not match or match.status in ("completed", "walkover"):
            continue
        
        # Calculate makeup deadline based on round_deadline or fallback to legacy Wednesday
        if match.round_deadline:
            # Makeup deadline = round_deadline + 3 days
            makeup_deadline = datetime.combine(
                match.round_deadline.date() + timedelta(days=3), 
                datetime.max.time()
            )
        else:
            # Fallback: Parse from proposed time and use legacy Wednesday logic
            if reschedule.proposed_time and " at " in reschedule.proposed_time:
                date_str = reschedule.proposed_time.split(" at ")[0]
                try:
                    proposed_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    proposed_weekday = proposed_date.weekday()
                    if proposed_weekday in [0, 1, 2]:  # Mon, Tue, Wed
                        days_to_wednesday = 2 - proposed_weekday
                        wednesday_of_week = proposed_date + timedelta(days=days_to_wednesday)
                        makeup_deadline = datetime.combine(wednesday_of_week, datetime.max.time())
                    else:
                        continue  # Can't determine deadline, skip
                except ValueError:
                    continue  # Invalid date format, skip
            else:
                continue  # No proposed time, skip
        
        # Check if makeup deadline has passed
        if now > makeup_deadline:
            # Apply walkover - opponent wins
            opponent_id = match.team_b_id if match.team_a_id == reschedule.requester_team_id else match.team_a_id
            opponent_team = Team.query.get(opponent_id)
            requester_team = Team.query.get(reschedule.requester_team_id)

            if opponent_team and requester_team:
                # Award walkover win (typical score: 6-0, 6-0)
                match.status = "completed"
                match.verified = True
                match.winner_id = opponent_id

                # Set scores from perspectives
                if match.team_a_id == opponent_id:
                    match.score_a = "6-0, 6-0"
                    match.score_b = "0-6, 0-6"
                    match.sets_a = 2
                    match.sets_b = 0
                    match.games_a = 12
                    match.games_b = 0
                else:
                    match.score_a = "0-6, 0-6"
                    match.score_b = "6-0, 6-0"
                    match.sets_a = 0
                    match.sets_b = 2
                    match.games_a = 0
                    match.games_b = 12

                # Update team stats
                update_team_stats_from_match(match)

                # Mark reschedule as expired
                reschedule.status = "expired_walkover"

                walkovers_applied['makeup'].append({
                    'match_id': match.id,
                    'round': match.round,
                    'requester_team': requester_team.team_name,
                    'opponent_team': opponent_team.team_name,
                    'deadline': makeup_deadline.strftime("%A, %B %d at %H:%M"),
                    'type': 'makeup'
                })

    # ========================================
    # 2. Check REGULAR MATCH deadlines (Sunday 23:59)
    # ========================================
    # Get all non-completed matches that don't have pending reschedules
    rescheduled_match_ids = [r.match_id for r in pending_reschedules]

    # Find matches that should have been completed by last Sunday
    all_matches = Match.query.filter(Match.status.notin_(["completed", "walkover"])).all()

    for match in all_matches:
        # Skip if this match has a pending reschedule (it gets Wednesday deadline)
        if match.id in rescheduled_match_ids:
            continue

        # Skip if match doesn't have a round or match_date
        if not match.round:
            continue

        # Use round_deadline from match if set, otherwise fall back to calculated Sunday
        if match.round_deadline:
            # Use the explicitly set round deadline
            round_deadline = datetime.combine(match.round_deadline.date(), datetime.max.time())
        else:
            # Calculate the Sunday deadline for this round (fallback)
            # Assuming rounds start on Monday, we need to find the Sunday of that week
            round_start_date = get_round_start_date(match.round)
            if round_start_date:
                # Find the Sunday of that week (6 days after Monday)
                sunday_of_week = round_start_date + timedelta(days=6)
                round_deadline = datetime.combine(sunday_of_week, datetime.max.time())
            else:
                continue  # Can't determine deadline, skip
        
        # Check if deadline has passed
        if now > round_deadline:
            # Apply walkover - both teams lose (or could be draw, your choice)
            # For now, let's apply walkover to Team B (Team A wins by default)
            # In real scenario, admin should manually review these

            team_a = Team.query.get(match.team_a_id)
            team_b = Team.query.get(match.team_b_id)

            if team_a and team_b:
                # Award walkover to Team A (arbitrary choice - admin can override)
                match.status = "completed"
                match.verified = True
                match.winner_id = match.team_a_id

                match.score_a = "6-0, 6-0"
                match.score_b = "0-6, 0-6"
                match.sets_a = 2
                match.sets_b = 0
                match.games_a = 12
                match.games_b = 0

                # Update team stats
                update_team_stats_from_match(match)

                walkovers_applied['regular'].append({
                    'match_id': match.id,
                    'round': match.round,
                    'team_a': team_a.team_name,
                    'team_b': team_b.team_name,
                    'deadline': round_deadline.strftime("%A, %B %d at %H:%M"),
                    'type': 'regular'
                })

    if walkovers_applied['regular'] or walkovers_applied['makeup']:
        db.session.commit()

    return walkovers_applied


def get_round_start_date(round_number):
    """
    Calculate the Monday start date for a given round number
    Round 1 starts November 17, 2025 (Monday)
    """
    from datetime import datetime, timedelta
    if not round_number:
        return None
    round_1_start = datetime(2025, 11, 17).date()  # November 17, 2025 (Monday)
    round_start = round_1_start + timedelta(weeks=round_number - 1)
    return round_start


def check_reschedule_conflicts(proposed_matches):
    """Check if proposed matches conflict with pending reschedules"""
    pending_reschedules = get_pending_reschedules()
    conflicts = []

    for match in proposed_matches:
        team_a_id = match.get('team_a_id')
        team_b_id = match.get('team_b_id')

        # Check if either team has pending reschedules
        for reschedule in pending_reschedules:
            if reschedule.match_id:
                existing_match = Match.query.get(reschedule.match_id)
                if existing_match:
                    # Check if this proposed match conflicts with a pending reschedule
                    if (team_a_id in [existing_match.team_a_id, existing_match.team_b_id] or
                        team_b_id in [existing_match.team_a_id, existing_match.team_b_id]):
                        conflicts.append({
                            'proposed_match': match,
                            'conflicting_reschedule': reschedule,
                            'conflicting_teams': [team_a_id, team_b_id]
                        })

    return conflicts


def find_team_by_phone(phone_digits: str) -> Team | None:
    if not phone_digits:
        return None
    # Match by suffix to be lenient with country codes
    all_teams = Team.query.all()
    for t in all_teams:
        p1 = digits_only(t.player1_phone)
        p2 = digits_only(t.player2_phone)
        if phone_digits.endswith(p1) and p1:
            return t
        if phone_digits.endswith(p2) and p2:
            return t
    return None

@app.route("/health")
def health():
    """Fast health check endpoint for deployment monitoring"""
    return {"status": "ok"}, 200

@app.route("/")
def index():
    league_teams = Team.query.count()
    ladder_men_teams = LadderTeam.query.filter_by(gender='men').count()
    ladder_women_teams = LadderTeam.query.filter_by(gender='women').count()
    ladder_free_agents = LadderFreeAgent.query.count()
    return render_template("index.html", 
                         league_teams=league_teams,
                         ladder_men_teams=ladder_men_teams,
                         ladder_women_teams=ladder_women_teams,
                         ladder_free_agents=ladder_free_agents)

@app.route("/register-team", methods=["GET", "POST"])
def register_team():
    # Check if team registration is open
    settings = LeagueSettings.query.first()
    if settings and not settings.team_registration_open:
        return render_template("registration_closed.html", registration_type="Team")

    if request.method == "POST":
        team_name = request.form["team_name"]
        p1_name = request.form["player1_name"]
        p1_phone = request.form["player1_phone"]
        p1_email = request.form.get("player1_email", "").strip()
        p2_name = request.form["player2_name"]
        p2_phone = request.form["player2_phone"]
        p2_email = request.form.get("player2_email", "").strip()

        # Require emails for both players
        if not p1_email or not p2_email:
            flash("Email is required for both players.", "error")
            return render_template("register_team.html", form_data=request.form)

        # Check if Player 1 and Player 2 have the same email or phone number
        if p1_email.lower() == p2_email.lower():
            flash("Player 1 and Player 2 cannot have the same email address.", "error")
            return render_template("register_team.html", form_data=request.form)

        if normalize_phone_number(p1_phone) == normalize_phone_number(p2_phone):
            flash("Player 1 and Player 2 cannot have the same WhatsApp number.", "error")
            return render_template("register_team.html", form_data=request.form)

        # Check if Player 1's email or phone is already registered in another team
        existing_team_p1_email = Team.query.filter(
            db.or_(
                Team.player1_email == p1_email,
                Team.player2_email == p1_email
            )
        ).first()

        if existing_team_p1_email:
            flash(f"Player 1's email ({p1_email}) is already registered in team '{existing_team_p1_email.team_name}'. Each player can only be in one team.", "error")
            return render_template("register_team.html", form_data=request.form)

        p1_phone_normalized = normalize_phone_number(p1_phone)
        existing_team_p1_phone = Team.query.filter(
            db.or_(
                Team.player1_phone == p1_phone_normalized,
                Team.player2_phone == p1_phone_normalized
            )
        ).first()

        if existing_team_p1_phone:
            flash(f"Player 1's WhatsApp number is already registered in team '{existing_team_p1_phone.team_name}'. Each player can only be in one team.", "error")
            return render_template("register_team.html", form_data=request.form)

        # Check if Player 2's email or phone is already registered in another team
        existing_team_p2_email = Team.query.filter(
            db.or_(
                Team.player1_email == p2_email,
                Team.player2_email == p2_email
            )
        ).first()

        if existing_team_p2_email:
            flash(f"Player 2's email ({p2_email}) is already registered in team '{existing_team_p2_email.team_name}'. Each player can only be in one team.", "error")
            return render_template("register_team.html", form_data=request.form)

        p2_phone_normalized = normalize_phone_number(p2_phone)
        existing_team_p2_phone = Team.query.filter(
            db.or_(
                Team.player1_phone == p2_phone_normalized,
                Team.player2_phone == p2_phone_normalized
            )
        ).first()

        if existing_team_p2_phone:
            flash(f"Player 2's WhatsApp number is already registered in team '{existing_team_p2_phone.team_name}'. Each player can only be in one team.", "error")
            return render_template("register_team.html", form_data=request.form)

        # Enforce unique team names using canonical form
        canonical = normalize_team_name(team_name)
        existing = Team.query.filter_by(team_name_canonical=canonical).first()
        if existing:
            flash("A team with a similar name already exists. Please choose a unique name.", "error")
            return render_template("register_team.html", form_data=request.form)

        # Generate unique access token for this team
        access_token = secrets.token_urlsafe(32)
        # Generate confirmation token for Player 2
        player2_confirmation_token = secrets.token_urlsafe(32)

        # Normalize phone numbers before storing
        p1_phone_normalized = normalize_phone_number(p1_phone)
        p2_phone_normalized = normalize_phone_number(p2_phone)

        new_team = Team(team_name=team_name, team_name_canonical=canonical,
                        player1_name=p1_name, player1_phone=p1_phone_normalized, player1_email=p1_email,
                        player2_name=p2_name, player2_phone=p2_phone_normalized, player2_email=p2_email,
                        access_token=access_token,
                        player2_confirmation_token=player2_confirmation_token,
                        player2_confirmed=False)  # Player 2 needs to confirm
        db.session.add(new_team)
        db.session.commit()

        # Create or update Player records for both players
        from datetime import datetime
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Player 1
        player1 = Player.query.filter_by(phone=p1_phone).first()
        if not player1:
            player1 = Player(
                name=p1_name,
                phone=p1_phone,
                email=p1_email,
                current_team_id=new_team.id,
                created_at=now
            )
            db.session.add(player1)
        else:
            player1.name = p1_name  # Update name in case it changed
            player1.current_team_id = new_team.id
            if p1_email:
                player1.email = p1_email

        # Player 2
        player2 = Player.query.filter_by(phone=p2_phone).first()
        if not player2:
            player2 = Player(
                name=p2_name,
                phone=p2_phone,
                email=p2_email,
                current_team_id=new_team.id,
                created_at=now
            )
            db.session.add(player2)
        else:
            player2.name = p2_name
            player2.current_team_id = new_team.id
            if p2_email:
                player2.email = p2_email

        db.session.commit()

        # Generate secure access link using custom domain
        base_url = "https://goeclectic.xyz"
        access_link = f"{base_url}/my-matches/{access_token}"
        confirmation_link = f"{base_url}/confirm-team/{new_team.id}/{player2_confirmation_token}"

        # Send admin notification about new team registration
        admin_email = os.environ.get("ADMIN_EMAIL")
        if admin_email:
            from utils import send_email_notification
            admin_body = f"""🆕 NEW TEAM REGISTRATION

Team Name: {team_name}

Player 1:
- Name: {p1_name}
- Email: {p1_email}
- Phone: {p1_phone}

Player 2:
- Name: {p2_name}
- Email: {p2_email}
- Phone: {p2_phone}

Access Link: {access_link}
Confirmation Link for Player 2: {confirmation_link}

Please review and confirm this team in the admin panel.
"""
            send_email_notification(admin_email, f"New Team Registration: {team_name}", admin_body)

        # Send confirmation email to Player 1 (registrant)
        if p1_email:
            from utils import send_email_notification
            email_body = f"""Hi {p1_name},

✅ Your team "{team_name}" has been successfully registered!

📋 Registration Details:
- Team Name: {team_name}
- Player 1: {p1_name} (You)
- Player 2: {p2_name}

⏳ Next Step: Waiting for {p2_name} to confirm the partnership
We've sent a confirmation link to {p2_name}'s email ({p2_email}). Once they confirm, your team will be active and ready to compete!

🔗 Your Team Access Link:
{access_link}

Bookmark this link to:
- View your match schedule
- See opponent contact information
- Submit match scores
- Request reschedules or substitutes

💬 Join Our WhatsApp Community:
https://chat.whatsapp.com/FGOQG62XwWfDazc6ZmMagT

Stay connected with other teams, get updates, and coordinate matches!

Good luck in the league! 🎾

- BD Padel League
"""
            send_email_notification(p1_email, f"Team Registered - Awaiting Partner Confirmation", email_body)

        # Send confirmation email to Player 2 if email provided
        if p2_email:
            from utils import send_email_notification
            email_body = f"""Hi {p2_name},

You've been invited to join the BD Padel League team "{team_name}" by {p1_name}.

Please confirm your partnership by clicking the link below:
{confirmation_link}

Or visit your team page:
{access_link}

Once confirmed, you'll be able to participate in matches!

💬 Join Our WhatsApp Community:
https://chat.whatsapp.com/FGOQG62XwWfDazc6ZmMagT

Stay connected with other teams, get updates, and coordinate matches!

- BD Padel League
"""
            send_email_notification(p2_email, f"Confirm Your Partnership - Team {team_name}", email_body)

        flash(f"Team registered successfully! {p2_name} will receive a confirmation link.", "success")
        return redirect(url_for("index"))
    return render_template("register_team.html")

@app.route("/confirm-team/<int:team_id>/<token>", methods=["GET", "POST"])
def confirm_team_partnership(team_id: int, token: str):
    """Player 2 confirms their partnership via secure link"""
    team = Team.query.get_or_404(team_id)

    # Verify token matches
    if team.player2_confirmation_token != token:
        flash("Invalid confirmation link. Please check your link or contact admin.", "error")
        return redirect(url_for("index"))

    # Check if already confirmed
    if team.player2_confirmed:
        return render_template("confirm_team.html", team=team, already_confirmed=True)

    if request.method == "POST":
        # Player 2 confirms
        team.player2_confirmed = True
        team.confirmed = True  # Team is now fully confirmed
        db.session.commit()

        # Notify Player 1
        from utils import send_email_notification

        base_url = "https://goeclectic.xyz"
        access_link = f"{base_url}/my-matches/{team.access_token}"

        if team.player1_email:
            email_body = f"""Hi {team.player1_name},

Great news! {team.player2_name} has confirmed your partnership.

Team "{team.team_name}" is now active and ready to participate in matches!

Visit your team page: {access_link}

Good luck!

- BD Padel League
"""
            send_email_notification(team.player1_email, f"Partnership Confirmed - Team {team.team_name}", email_body)

        flash(f"✅ Partnership confirmed! Team {team.team_name} is now active.", "success")
        return redirect(f"/my-matches/{team.access_token}")

    return render_template("confirm_team.html", team=team, already_confirmed=False)

@app.route("/register-freeagent", methods=["GET", "POST"])
def register_freeagent():
    """
    DEPRECATED: League free agent registration has been moved to the Ladder system.
    This route now redirects to the ladder free agent registration.
    """
    flash("ℹ️ Free agent registration has moved to our Ladder system for better matching and ongoing play opportunities!", "info")
    return redirect(url_for("ladder_register_freeagent"))

@app.route("/ladder/register-team", methods=["GET", "POST"])
def ladder_register_team():
    """Ladder team registration with gender and contact preferences"""
    if request.method == "POST":
        team_name = request.form["team_name"]
        p1_name = request.form["player1_name"]
        p1_phone = request.form["player1_phone"]
        p1_email = request.form.get("player1_email", "").strip()
        p2_name = request.form["player2_name"]
        p2_phone = request.form["player2_phone"]
        p2_email = request.form.get("player2_email", "").strip()
        gender = request.form.get("gender", "").strip()

        # Get contact preferences
        contact_email = request.form.get("contact_email") == "on"
        contact_whatsapp = request.form.get("contact_whatsapp") == "on"

        # Validate required fields
        if not p1_email or not p2_email:
            flash("Email is required for both players.", "error")
            return render_template("ladder/register_team.html", form_data=request.form)

        if not gender or gender not in ["men", "women", "mixed"]:
            flash("Please select a division (Men, Women, or Mixed).", "error")
            return render_template("ladder/register_team.html", form_data=request.form)
        
        # For Mixed teams, validate gender selections
        player1_gender = None
        player2_gender = None
        if gender == "mixed":
            player1_gender = request.form.get("player1_gender", "").strip()
            player2_gender = request.form.get("player2_gender", "").strip()
            
            if not player1_gender or not player2_gender:
                flash("Please select gender for both players in Mixed teams.", "error")
                return render_template("ladder/register_team.html", form_data=request.form)
            
            if player1_gender not in ["male", "female"] or player2_gender not in ["male", "female"]:
                flash("Invalid gender selection.", "error")
                return render_template("ladder/register_team.html", form_data=request.form)
            
            # Validate exactly one male and one female
            if player1_gender == player2_gender:
                flash("Mixed teams must have exactly one male and one female player.", "error")
                return render_template("ladder/register_team.html", form_data=request.form)

        # Validate at least one contact preference
        if not contact_email and not contact_whatsapp:
            flash("Please select at least one contact preference (Email or WhatsApp).", "error")
            return render_template("ladder/register_team.html", form_data=request.form)

        # Check if Player 1 and Player 2 have the same email or phone number
        if p1_email.lower() == p2_email.lower():
            flash("Player 1 and Player 2 cannot have the same email address.", "error")
            return render_template("ladder/register_team.html", form_data=request.form)

        if normalize_phone_number(p1_phone) == normalize_phone_number(p2_phone):
            flash("Player 1 and Player 2 cannot have the same WhatsApp number.", "error")
            return render_template("ladder/register_team.html", form_data=request.form)

        # Normalize phone numbers
        p1_phone_normalized = normalize_phone_number(p1_phone)
        p2_phone_normalized = normalize_phone_number(p2_phone)

        # Check team name uniqueness against BOTH Team and LadderTeam tables
        canonical = normalize_team_name(team_name)
        existing_league_team = Team.query.filter_by(team_name_canonical=canonical).first()
        existing_ladder_team = LadderTeam.query.filter_by(team_name_canonical=canonical).first()

        if existing_league_team or existing_ladder_team:
            flash("A team with a similar name already exists. Please choose a unique name.", "error")
            return render_template("ladder/register_team.html", form_data=request.form)

        # For Mixed ladder, only check if player already exists in another MIXED team
        # Allow registration even if they're in league or men's/women's ladder
        if gender == 'mixed':
            # Check Player 1 email only in Mixed ladder teams
            existing_mixed_p1_email = LadderTeam.query.filter(
                db.or_(
                    LadderTeam.player1_email == p1_email,
                    LadderTeam.player2_email == p1_email
                ),
                LadderTeam.gender == 'mixed'
            ).first()

            if existing_mixed_p1_email:
                flash(f"Player 1's email ({p1_email}) is already registered in mixed team '{existing_mixed_p1_email.team_name}'. Each player can only be in one mixed team.", "error")
                return render_template("ladder/register_team.html", form_data=request.form)

            # Check Player 1 phone only in Mixed ladder teams
            existing_mixed_p1_phone = LadderTeam.query.filter(
                db.or_(
                    LadderTeam.player1_phone == p1_phone_normalized,
                    LadderTeam.player2_phone == p1_phone_normalized
                ),
                LadderTeam.gender == 'mixed'
            ).first()

            if existing_mixed_p1_phone:
                flash(f"Player 1's WhatsApp number is already registered in mixed team '{existing_mixed_p1_phone.team_name}'. Each player can only be in one mixed team.", "error")
                return render_template("ladder/register_team.html", form_data=request.form)

            # Check Player 2 email only in Mixed ladder teams
            existing_mixed_p2_email = LadderTeam.query.filter(
                db.or_(
                    LadderTeam.player1_email == p2_email,
                    LadderTeam.player2_email == p2_email
                ),
                LadderTeam.gender == 'mixed'
            ).first()

            if existing_mixed_p2_email:
                flash(f"Player 2's email ({p2_email}) is already registered in mixed team '{existing_mixed_p2_email.team_name}'. Each player can only be in one mixed team.", "error")
                return render_template("ladder/register_team.html", form_data=request.form)

            # Check Player 2 phone only in Mixed ladder teams
            existing_mixed_p2_phone = LadderTeam.query.filter(
                db.or_(
                    LadderTeam.player1_phone == p2_phone_normalized,
                    LadderTeam.player2_phone == p2_phone_normalized
                ),
                LadderTeam.gender == 'mixed'
            ).first()

            if existing_mixed_p2_phone:
                flash(f"Player 2's WhatsApp number is already registered in mixed team '{existing_mixed_p2_phone.team_name}'. Each player can only be in one mixed team.", "error")
                return render_template("ladder/register_team.html", form_data=request.form)

        else:
            # For Men's and Women's ladder, only check within ladder teams (allow league players)
            # Check Player 1 email in LadderTeam only
            existing_ladder_p1_email = LadderTeam.query.filter(
                db.or_(
                    LadderTeam.player1_email == p1_email,
                    LadderTeam.player2_email == p1_email
                )
            ).first()

            if existing_ladder_p1_email:
                flash(f"Player 1's email ({p1_email}) is already registered in ladder team '{existing_ladder_p1_email.team_name}'. Each player can only be in one ladder team.", "error")
                return render_template("ladder/register_team.html", form_data=request.form)

            # Check Player 1 phone in LadderTeam only
            existing_ladder_p1_phone = LadderTeam.query.filter(
                db.or_(
                    LadderTeam.player1_phone == p1_phone_normalized,
                    LadderTeam.player2_phone == p1_phone_normalized
                )
            ).first()

            if existing_ladder_p1_phone:
                flash(f"Player 1's WhatsApp number is already registered in ladder team '{existing_ladder_p1_phone.team_name}'. Each player can only be in one ladder team.", "error")
                return render_template("ladder/register_team.html", form_data=request.form)

            # Check Player 2 email in LadderTeam only
            existing_ladder_p2_email = LadderTeam.query.filter(
                db.or_(
                    LadderTeam.player1_email == p2_email,
                    LadderTeam.player2_email == p2_email
                )
            ).first()

            if existing_ladder_p2_email:
                flash(f"Player 2's email ({p2_email}) is already registered in ladder team '{existing_ladder_p2_email.team_name}'. Each player can only be in one ladder team.", "error")
                return render_template("ladder/register_team.html", form_data=request.form)

            # Check Player 2 phone in LadderTeam only
            existing_ladder_p2_phone = LadderTeam.query.filter(
                db.or_(
                    LadderTeam.player1_phone == p2_phone_normalized,
                    LadderTeam.player2_phone == p2_phone_normalized
                )
            ).first()

            if existing_ladder_p2_phone:
                flash(f"Player 2's WhatsApp number is already registered in ladder team '{existing_ladder_p2_phone.team_name}'. Each player can only be in one ladder team.", "error")
                return render_template("ladder/register_team.html", form_data=request.form)

        # Generate unique access token
        access_token = secrets.token_urlsafe(32)

        # Find max rank in the appropriate gender ladder and add team at bottom
        from datetime import datetime
        max_rank_team = LadderTeam.query.filter_by(
            gender=gender
        ).order_by(LadderTeam.current_rank.desc()).first()

        current_rank = max_rank_team.current_rank + 1 if max_rank_team else 1

        # Create new ladder team
        new_team = LadderTeam(
            team_name=team_name,
            team_name_canonical=canonical,
            player1_name=p1_name,
            player1_phone=p1_phone_normalized,
            player1_email=p1_email,
            player2_name=p2_name,
            player2_phone=p2_phone_normalized,
            player2_email=p2_email,
            gender=gender,
            ladder_type=gender,
            current_rank=current_rank,
            contact_preference_email=contact_email,
            contact_preference_whatsapp=contact_whatsapp,
            access_token=access_token,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            player1_gender=player1_gender if gender == "mixed" else None,
            player2_gender=player2_gender if gender == "mixed" else None
        )
        db.session.add(new_team)
        db.session.commit()

        # Generate access link
        base_url = "https://goeclectic.xyz"
        access_link = f"{base_url}/ladder/my-team/{access_token}"

        # Send confirmation email to Player 1
        if p1_email:
            from utils import send_email_notification
            # Determine WhatsApp group link based on gender
            if gender == 'men':
                whatsapp_link = "https://chat.whatsapp.com/Fw54Nxdk6jS9GTMOTnC0UD"
            elif gender == 'women':
                whatsapp_link = "https://chat.whatsapp.com/GswFleVQhxF4gziShBhstd"
            else:  # mixed
                whatsapp_link = "https://chat.whatsapp.com/LMHJyJ68MeCEhZaewOA8jx"

            email_body = f"""Hi {p1_name},

✅ Your team "{team_name}" has been successfully registered for the Ladder Tournament!

📋 Registration Details:
- Team Name: {team_name}
- Gender Category: {gender.capitalize()}
- Player 1: {p1_name} (You)
- Player 2: {p2_name}
- Starting Rank: #{current_rank}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💳 PAYMENT REQUIRED - IMPORTANT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

To complete your registration and be listed on the ladder rankings, please make a payment of BDT 500 PER TEAM (NOT per player).

Payment Method: bKash
Payment Number: 01313399918
Amount: BDT 500 (TOTAL FOR THE ENTIRE TEAM - split between both players if you wish)

⚠️ IMPORTANT: 
1. This is BDT 500 for the WHOLE TEAM (both players together)
2. You can split the cost between players or one player can pay the full amount
3. When making the payment, you MUST put your team name in the reference/note field:

Reference: {team_name}

Failure to include your team name in the reference may cause delays in listing your team on the ladder rankings.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Once payment is confirmed by admin, your team will be visible on the ladder rankings and you can start challenging other teams.

🔗 Your Team Access Link:
{access_link}

🔑 Access Token (for team login page):
{access_token}

You can either:
1. Click the access link above to go directly to your team page, OR
2. Visit the ladder login page and paste your access token

💬 Join Your Division's WhatsApp Group:
{whatsapp_link}

Stay connected with other teams, coordinate matches, and get updates!

🎾 How the Ladder Works:
- Challenge teams up to 3 positions above you
- Win to swap positions and climb the ladder
- Play at your convenience
- Monthly Americano tournaments for additional fun!

Good luck climbing the ladder! 🚀

- BD Padel League
"""
            send_email_notification(p1_email, f"Ladder Team Registered - {team_name}", email_body)

        # Send confirmation email to Player 2
        if p2_email:
            from utils import send_email_notification
            email_body = f"""Hi {p2_name},

✅ You've been registered as part of team "{team_name}" for the Ladder Tournament!

📋 Team Details:
- Team Name: {team_name}
- Gender Category: {gender.capitalize()}
- Partner: {p1_name}
- Starting Rank: #{current_rank}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💳 PAYMENT REQUIRED - IMPORTANT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

To complete your registration and be listed on the ladder rankings, please make a payment of BDT 500 PER TEAM (NOT per player).

Payment Method: bKash
Payment Number: 01313399918
Amount: BDT 500 (TOTAL FOR THE ENTIRE TEAM - split between both players if you wish)

⚠️ IMPORTANT: 
1. This is BDT 500 for the WHOLE TEAM (both players together)
2. You can coordinate with {p1_name} to split the cost or one of you can pay the full amount
3. When making the payment, you MUST put your team name in the reference/note field:

Reference: {team_name}

Failure to include your team name in the reference may cause delays in listing your team on the ladder rankings.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Once payment is confirmed by admin, your team will be visible on the ladder rankings and you can start challenging other teams.

🔗 Your Team Access Link:
{access_link}

🔑 Access Token (for team login page):
{access_token}

You can either:
1. Click the access link above to go directly to your team page, OR
2. Visit the ladder login page and paste your access token

💬 Join Your Division's WhatsApp Group:
{whatsapp_link}

Stay connected with other teams, coordinate matches, and get updates!

🎾 How the Ladder Works:
- Challenge teams up to 3 positions above you
- Win to swap positions and climb the ladder
- Play at your convenience
- Monthly Americano tournaments for additional fun!

Good luck climbing the ladder! 🚀

- BD Padel League
"""
            send_email_notification(p2_email, f"Ladder Team Registered - {team_name}", email_body)

        # Send admin notification
        admin_email = os.environ.get("ADMIN_EMAIL")
        if admin_email:
            from utils import send_email_notification
            admin_body = f"""🆕 NEW LADDER TEAM REGISTRATION

Team Name: {team_name}
Gender: {gender.capitalize()}
Ladder Type: Ladder
Starting Rank: #{current_rank}

Player 1:
- Name: {p1_name}
- Email: {p1_email}
- Phone: {p1_phone}

Player 2:
- Name: {p2_name}
- Email: {p2_email}
- Phone: {p2_phone}

Contact Preferences:
- Email: {"Yes" if contact_email else "No"}
- WhatsApp: {"Yes" if contact_whatsapp else "No"}

Access Link: {access_link}
"""
            send_email_notification(admin_email, f"New Ladder Team: {team_name}", admin_body)

        return render_template("ladder/registration_success_team.html", 
                             team_name=team_name, 
                             access_link=access_link,
                             rank=current_rank,
                             gender=gender)

    return render_template("ladder/register_team.html")

@app.route("/ladder/register-freeagent", methods=["GET", "POST"])
def ladder_register_freeagent():
    """Ladder free agent registration for monthly Americano tournaments"""
    if request.method == "POST":
        name = request.form["name"]
        phone = request.form["phone"]
        email = request.form.get("email", "").strip()
        gender = request.form.get("gender", "").strip()
        skill_level = request.form.get("skill_level", "").strip()
        playstyle = request.form.get("playstyle", "").strip()
        availability = request.form.get("availability", "").strip()

        # Get contact preferences
        contact_email = request.form.get("contact_email") == "on"
        contact_whatsapp = request.form.get("contact_whatsapp") == "on"

        # Validate required fields
        if not email:
            flash("Email is required for free agent registration.", "error")
            return render_template("ladder/register_freeagent.html", form_data=request.form)

        if not gender or gender not in ["men", "women"]:
            flash("Please select a gender (Men or Women).", "error")
            return render_template("ladder/register_freeagent.html", form_data=request.form)

        # Validate at least one contact preference
        if not contact_email and not contact_whatsapp:
            flash("Please select at least one contact preference (Email or WhatsApp).", "error")
            return render_template("ladder/register_freeagent.html", form_data=request.form)

        # Normalize phone number
        phone_normalized = normalize_phone_number(phone)

        # Check if email is already registered in LadderTeam only (allow league players)
        existing_ladder_email = LadderTeam.query.filter(
            db.or_(
                LadderTeam.player1_email == email,
                LadderTeam.player2_email == email
            )
        ).first()

        if existing_ladder_email:
            flash(f"This email ({email}) is already registered in ladder team '{existing_ladder_email.team_name}'. Please use a different email.", "error")
            return render_template("ladder/register_freeagent.html", form_data=request.form)

        # Check if phone is already registered in LadderTeam only (allow league players)
        existing_ladder_phone = LadderTeam.query.filter(
            db.or_(
                LadderTeam.player1_phone == phone_normalized,
                LadderTeam.player2_phone == phone_normalized
            )
        ).first()

        if existing_ladder_phone:
            flash(f"This WhatsApp number is already registered in ladder team '{existing_ladder_phone.team_name}'. Please use a different number.", "error")
            return render_template("ladder/register_freeagent.html", form_data=request.form)

        # Check ladder free agents (duplicate within ladder free agents only)
        existing_ladder_fa_email = LadderFreeAgent.query.filter_by(email=email).first()
        if existing_ladder_fa_email:
            flash(f"This email is already registered as a ladder free agent. Please use a different email.", "error")
            return render_template("ladder/register_freeagent.html", form_data=request.form)

        existing_ladder_fa_phone = LadderFreeAgent.query.filter_by(phone=phone_normalized).first()
        if existing_ladder_fa_phone:
            flash(f"This WhatsApp number is already registered as a ladder free agent. Please use a different number.", "error")
            return render_template("ladder/register_freeagent.html", form_data=request.form)

        # Generate unique access token
        access_token = secrets.token_urlsafe(32)

        # Create new ladder free agent
        from datetime import datetime
        new_fa = LadderFreeAgent(
            name=name,
            phone=phone_normalized,
            email=email,
            gender=gender,
            contact_preference_email=contact_email,
            contact_preference_whatsapp=contact_whatsapp,
            access_token=access_token,
            skill_level=skill_level,
            playstyle=playstyle,
            availability=availability,
            created_at=datetime.now()
        )
        db.session.add(new_fa)
        db.session.commit()

        # Generate access link
        base_url = "https://goeclectic.xyz"
        access_link = f"{base_url}/ladder/my-team/{access_token}"

        # Send confirmation email
        if email:
            from utils import send_email_notification
            # Determine WhatsApp group link based on gender
            if gender == 'men':
                whatsapp_link = "https://chat.whatsapp.com/BMqHxbPhKg67tmXIyuZwNJ"
            else:
                whatsapp_link = "https://chat.whatsapp.com/JdjNaMf3QhnD7yw1saq9lk"

            email_body = f"""Hi {name},

✅ Welcome to the Ladder Tournament! Your free agent registration has been confirmed.

📋 Your Profile:
- Name: {name}
- Gender: {gender.capitalize()}
- Skill Level: {skill_level}
- Playstyle: {playstyle}
- Availability: {availability}

🎾 Monthly Americano Tournaments:
As a ladder free agent, you'll be invited to participate in our monthly Americano tournaments! These are fun, social tournaments where you'll:
- Play with different partners each round
- Meet other players in your gender category
- Compete for prizes and bragging rights
- Enjoy a friendly, competitive atmosphere

💬 Join Your Free Agents WhatsApp Group:
{whatsapp_link}

Connect with other free agents, get tournament updates, and find potential partners!

📅 What's Next?
You'll receive an email notification before each monthly tournament with:
- Tournament date and time
- Registration confirmation
- Tournament format details
- Venue information

Contact Preferences: {"Email" if contact_email else ""}{"" if not (contact_email and contact_whatsapp) else " and "}{"WhatsApp" if contact_whatsapp else ""}

If you have any questions, please contact the admin.

Thank you for joining! 🚀

- BD Padel League
"""
            send_email_notification(email, f"Ladder Free Agent Registration Confirmed", email_body)

        # Send admin notification
        admin_email = os.environ.get("ADMIN_EMAIL")
        if admin_email:
            from utils import send_email_notification
            admin_body = f"""🆕 NEW LADDER FREE AGENT REGISTRATION

Name: {name}
Email: {email}
Phone: {phone}
Gender: {gender.capitalize()}
Skill Level: {skill_level}
Playstyle: {playstyle}
Availability: {availability}

Contact Preferences:
- Email: {"Yes" if contact_email else "No"}
- WhatsApp: {"Yes" if contact_whatsapp else "No"}

Access Link: {access_link}
"""
            send_email_notification(admin_email, f"New Ladder Free Agent: {name}", admin_body)

        return render_template("ladder/registration_success_freeagent.html", 
                             name=name, 
                             access_link=access_link,
                             gender=gender)

    return render_template("ladder/register_freeagent.html")

@app.route("/ladder/men/")
def ladder_men():
    """Public Men's Ladder Rankings Page - View Only"""
    ladder_type = 'men'

    # Query by gender='men' and only show paid teams
    teams = LadderTeam.query.filter_by(
        gender='men',
        payment_received=True
    ).all()

    # Calculate initial rank based on registration order (when they joined)
    teams_by_creation = sorted(teams, key=lambda t: t.created_at)
    initial_ranks = {team.id: idx for idx, team in enumerate(teams_by_creation, start=1)}
    
    # Sort by current_rank (which preserves rank swaps from matches)
    # If current_rank is None, assign based on registration order
    teams_sorted = sorted(teams, key=lambda t: t.current_rank if t.current_rank is not None else initial_ranks.get(t.id, 999))
    
    # Assign display ranks (sequential 1..N for consistent display)
    for idx, team in enumerate(teams_sorted, start=1):
        team.display_rank = idx
    
    # Calculate movement: initial rank - current rank (positive = moved up)
    for team in teams:
        team.initial_rank = initial_ranks.get(team.id, 999)
        team.rank_movement = team.initial_rank - team.display_rank

    active_challenges = LadderChallenge.query.filter(
        LadderChallenge.ladder_type == ladder_type,
        LadderChallenge.status.in_(['pending_acceptance', 'accepted'])
    ).all()

    locked_team_ids = set()
    for challenge in active_challenges:
        locked_team_ids.add(challenge.challenger_team_id)
        locked_team_ids.add(challenge.challenged_team_id)

    recent_matches = LadderMatch.query.filter(
        LadderMatch.ladder_type == ladder_type,
        LadderMatch.verified == True
    ).order_by(LadderMatch.completed_at.desc()).limit(10).all()

    top_performers = []
    if teams_sorted:
        teams_with_matches = [t for t in teams_sorted if t.matches_played > 0]
        if teams_with_matches:
            sorted_by_wins = sorted(teams_with_matches, key=lambda t: (t.wins / t.matches_played if t.matches_played > 0 else 0, t.wins), reverse=True)
            top_performers = sorted_by_wins[:3]

    team_map = {t.id: t for t in teams_sorted}

    settings = LadderSettings.query.first()

    return render_template("ladder/ladder_rankings.html",
                         teams=teams_sorted,
                         ladder_type=ladder_type,
                         locked_team_ids=locked_team_ids,
                         recent_matches=recent_matches,
                         top_performers=top_performers,
                         team_map=team_map,
                         settings=settings,
                         is_public=True)

@app.route("/ladder/women/")
def ladder_women():
    """Public Women's Ladder Rankings Page - View Only"""
    ladder_type = 'women'

    # Query by gender='women' and only show paid teams
    teams = LadderTeam.query.filter_by(
        gender='women',
        payment_received=True
    ).all()

    # Calculate initial rank based on registration order (when they joined)
    teams_by_creation = sorted(teams, key=lambda t: t.created_at)
    initial_ranks = {team.id: idx for idx, team in enumerate(teams_by_creation, start=1)}
    
    # Sort by current_rank (which preserves rank swaps from matches)
    # If current_rank is None, assign based on registration order
    teams_sorted = sorted(teams, key=lambda t: t.current_rank if t.current_rank is not None else initial_ranks.get(t.id, 999))
    
    # Assign display ranks (sequential 1..N for consistent display)
    for idx, team in enumerate(teams_sorted, start=1):
        team.display_rank = idx
    
    # Calculate movement: initial rank - current rank (positive = moved up)
    for team in teams:
        team.initial_rank = initial_ranks.get(team.id, 999)
        team.rank_movement = team.initial_rank - team.display_rank

    active_challenges = LadderChallenge.query.filter(
        LadderChallenge.ladder_type == ladder_type,
        LadderChallenge.status.in_(['pending_acceptance', 'accepted'])
    ).all()

    locked_team_ids = set()
    for challenge in active_challenges:
        locked_team_ids.add(challenge.challenger_team_id)
        locked_team_ids.add(challenge.challenged_team_id)

    recent_matches = LadderMatch.query.filter(
        LadderMatch.ladder_type == ladder_type,
        LadderMatch.verified == True
    ).order_by(LadderMatch.completed_at.desc()).limit(10).all()

    top_performers = []
    if teams_sorted:
        teams_with_matches = [t for t in teams_sorted if t.matches_played > 0]
        if teams_with_matches:
            sorted_by_wins = sorted(teams_with_matches, key=lambda t: (t.wins / t.matches_played if t.matches_played > 0 else 0, t.wins), reverse=True)
            top_performers = sorted_by_wins[:3]

    team_map = {t.id: t for t in teams_sorted}

    settings = LadderSettings.query.first()

    return render_template("ladder/ladder_rankings.html",
                         teams=teams_sorted,
                         ladder_type=ladder_type,
                         locked_team_ids=locked_team_ids,
                         recent_matches=recent_matches,
                         top_performers=top_performers,
                         team_map=team_map,
                         settings=settings,
                         is_public=True)

@app.route("/ladder/mixed/")
def ladder_mixed():
    """Public Mixed Ladder Rankings Page - View Only"""
    ladder_type = 'mixed'

    # Query by gender='mixed' and only show paid teams
    teams = LadderTeam.query.filter_by(
        gender='mixed',
        payment_received=True
    ).all()
    
    # Calculate initial rank based on registration order (when they joined)
    teams_by_creation = sorted(teams, key=lambda t: t.created_at)
    initial_ranks = {team.id: idx for idx, team in enumerate(teams_by_creation, start=1)}
    
    # Sort by current_rank (which preserves rank swaps from matches)
    # If current_rank is None, assign based on registration order
    teams_sorted = sorted(teams, key=lambda t: t.current_rank if t.current_rank is not None else initial_ranks.get(t.id, 999))
    
    # Assign display ranks (sequential 1..N for consistent display)
    for idx, team in enumerate(teams_sorted, start=1):
        team.display_rank = idx
    
    # Calculate movement: initial rank - current rank (positive = moved up)
    for team in teams:
        team.initial_rank = initial_ranks.get(team.id, 999)
        team.rank_movement = team.initial_rank - team.display_rank

    active_challenges = LadderChallenge.query.filter(
        LadderChallenge.ladder_type == ladder_type,
        LadderChallenge.status.in_(['pending_acceptance', 'accepted'])
    ).all()

    locked_team_ids = set()
    for challenge in active_challenges:
        locked_team_ids.add(challenge.challenger_team_id)
        locked_team_ids.add(challenge.challenged_team_id)

    recent_matches = LadderMatch.query.filter(
        LadderMatch.ladder_type == ladder_type,
        LadderMatch.verified == True
    ).order_by(LadderMatch.completed_at.desc()).limit(10).all()

    top_performers = []
    if teams_sorted:
        teams_with_matches = [t for t in teams_sorted if t.matches_played > 0]
        if teams_with_matches:
            sorted_by_wins = sorted(teams_with_matches, key=lambda t: (t.wins / t.matches_played if t.matches_played > 0 else 0, t.wins), reverse=True)
            top_performers = sorted_by_wins[:3]

    team_map = {t.id: t for t in teams_sorted}

    settings = LadderSettings.query.first()

    # Check if user is logged in as a team
    logged_in_team = None
    if 'ladder_team_id' in session:
        logged_in_team = LadderTeam.query.get(session['ladder_team_id'])
        # Verify the team is in the mixed ladder
        if logged_in_team and logged_in_team.gender != 'mixed':
            logged_in_team = None

    return render_template("ladder/ladder_rankings.html",
                         teams=teams_sorted,
                         ladder_type=ladder_type,
                         locked_team_ids=locked_team_ids,
                         recent_matches=recent_matches,
                         top_performers=top_performers,
                         team_map=team_map,
                         settings=settings,
                         is_public=True,
                         logged_in_team=logged_in_team)

def apply_rank_penalty(team, penalty_amount, reason):
    """
    Apply rank penalty to a team and adjust other teams accordingly.

    Args:
        team: LadderTeam object to penalize
        penalty_amount: Number of ranks to move down (positive number)
        reason: String describing the penalty reason
    """
    from datetime import datetime
    from utils import send_email_notification

    # Check if penalties are active
    settings = LadderSettings.query.first()
    if not settings or not settings.penalties_active:
        return

    if penalty_amount <= 0:
        return

    old_rank = team.current_rank
    new_rank = old_rank + penalty_amount

    teams_in_ladder = LadderTeam.query.filter_by(ladder_type=team.ladder_type).all()
    max_rank = len(teams_in_ladder)

    if new_rank > max_rank:
        new_rank = max_rank

    teams_to_adjust = LadderTeam.query.filter(
        LadderTeam.ladder_type == team.ladder_type,
        LadderTeam.current_rank > old_rank,
        LadderTeam.current_rank <= new_rank,
        LadderTeam.id != team.id
    ).all()

    for t in teams_to_adjust:
        t.current_rank -= 1

    team.current_rank = new_rank

    db.session.commit()

    penalty_message = f"""Hi {team.player1_name},

LADDER PENALTY APPLIED

Your team "{team.team_name}" has received a rank penalty on the {team.ladder_type.title()} Ladder.

Penalty Details:
- Reason: {reason}
- Previous Rank: #{old_rank}
- New Rank: #{new_rank}
- Penalty: {penalty_amount} rank(s) down
- Date: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}

This penalty was automatically applied by the ladder system. If you have any questions or wish to dispute this penalty, please contact the league administrator at goeclecticbd@gmail.com.

Regards,
BD Padel Ladder Team
"""

    admin_email = "goeclecticbd@gmail.com"
    subject = f"Ladder Penalty Applied - {team.team_name}"

    if team.contact_preference_email:
        if team.player1_email:
            send_email_notification(team.player1_email, subject, penalty_message)
        if team.player2_email and team.player2_email != team.player1_email:
            send_email_notification(team.player2_email, subject, penalty_message)
        
        # CC Admin
        send_email_notification(admin_email, f"CC: {subject}", penalty_message)


def calculate_holiday_status(team, settings):
    """
    Calculate holiday mode status for a team.

    Args:
        team: LadderTeam object
        settings: LadderSettings object

    Returns:
        Dictionary with holiday status info or None if not on holiday
    """
    from datetime import datetime, timedelta

    if not team.holiday_mode_active or not team.holiday_mode_start:
        return None

    now = datetime.now()
    grace_period_days = settings.holiday_mode_grace_weeks * 7
    grace_period_end = team.holiday_mode_start + timedelta(days=grace_period_days)

    days_in_holiday = (now - team.holiday_mode_start).days
    grace_period_days_remaining = (grace_period_end - now).days

    weeks_beyond_grace = 0
    penalty_ranks = 0
    if grace_period_days_remaining < 0:
        days_beyond_grace = abs(grace_period_days_remaining)
        weeks_beyond_grace = (days_beyond_grace // 7) + (1 if days_beyond_grace % 7 > 0 else 0)
        penalty_ranks = weeks_beyond_grace * settings.holiday_mode_weekly_penalty_ranks

    return {
        'start_date': team.holiday_mode_start,
        'days_in_holiday': days_in_holiday,
        'grace_period_days_remaining': max(0, grace_period_days_remaining),
        'is_in_grace_period': grace_period_days_remaining >= 0,
        'weeks_beyond_grace': weeks_beyond_grace,
        'penalty_ranks': penalty_ranks
    }


def update_ladder_team_stats_from_match(match):
    """Update ladder team statistics after a verified match"""
    from datetime import datetime

    if match.stats_calculated:
        return

    team_a = LadderTeam.query.get(match.team_a_id)
    team_b = LadderTeam.query.get(match.team_b_id)

    if not team_a or not team_b:
        return

    team_a.sets_for += match.sets_a
    team_a.sets_against += match.sets_b
    team_a.games_for += match.games_a
    team_a.games_against += match.games_b

    team_b.sets_for += match.sets_b
    team_b.sets_against += match.sets_a
    team_b.games_for += match.games_b
    team_b.games_against += match.games_a

    if match.winner_id == team_a.id:
        team_a.wins += 1
        team_b.losses += 1
    elif match.winner_id == team_b.id:
        team_b.wins += 1
        team_a.losses += 1
    else:
        team_a.draws += 1
        team_b.draws += 1

    team_a.last_match_date = datetime.now()
    team_b.last_match_date = datetime.now()

    match.stats_calculated = True
    db.session.commit()


def swap_ladder_ranks(winner_team, loser_team, match):
    """
    Swap ladder ranks after a match result.
    Winner takes loser's rank, and all teams shift accordingly.

    Args:
        winner_team: LadderTeam object of the winning team
        loser_team: LadderTeam object of the losing team
        match: LadderMatch object

    Returns:
        dict with rank change information for logging and notifications
    """
    import logging

    winner_rank = winner_team.current_rank
    loser_rank = loser_team.current_rank
    ladder_type = winner_team.ladder_type

    logging.info(f"[RANK SWAP] Match ID {match.id}: {winner_team.team_name} (#{winner_rank}) vs {loser_team.team_name} (#{loser_rank})")

    if winner_rank == loser_rank:
        logging.warning(f"[RANK SWAP] Equal ranks detected (both #{winner_rank}) - no rank change")
        return {
            'winner_old_rank': winner_rank,
            'winner_new_rank': winner_rank,
            'loser_old_rank': loser_rank,
            'loser_new_rank': loser_rank,
            'teams_affected': []
        }

    all_teams = LadderTeam.query.filter_by(ladder_type=ladder_type).order_by(LadderTeam.current_rank).all()

    rank_changes = {
        'winner': {'old': winner_rank, 'new': 0},
        'loser': {'old': loser_rank, 'new': 0},
        'teams_affected': []
    }

    if winner_rank > loser_rank:
        logging.info(f"[RANK SWAP] Winner challenged UP: #{winner_rank} → #{loser_rank}")

        new_winner_rank = loser_rank
        new_loser_rank = loser_rank + 1

        for team in all_teams:
            if team.id == winner_team.id:
                team.current_rank = new_winner_rank
                logging.info(f"[RANK SWAP]   {team.team_name}: #{winner_rank} → #{new_winner_rank} (WINNER)")
            elif team.id == loser_team.id:
                team.current_rank = new_loser_rank
                logging.info(f"[RANK SWAP]   {team.team_name}: #{loser_rank} → #{new_loser_rank} (LOSER)")
            elif loser_rank <= team.current_rank < winner_rank:
                old_rank = team.current_rank
                team.current_rank = old_rank + 1
                logging.info(f"[RANK SWAP]   {team.team_name}: #{old_rank} → #{team.current_rank} (shifted down)")
                rank_changes['teams_affected'].append({
                    'team_name': team.team_name,
                    'old_rank': old_rank,
                    'new_rank': team.current_rank
                })

        rank_changes['winner']['new'] = new_winner_rank
        rank_changes['loser']['new'] = new_loser_rank

    elif winner_rank < loser_rank:
        logging.warning(f"[RANK SWAP] Winner challenged DOWN (unusual): #{winner_rank} beating #{loser_rank}")

        new_winner_rank = winner_rank
        new_loser_rank = loser_rank + 1

        for team in all_teams:
            if team.id == winner_team.id:
                team.current_rank = new_winner_rank
                logging.info(f"[RANK SWAP]   {team.team_name}: #{winner_rank} → #{new_winner_rank} (WINNER, no change)")
            elif team.id == loser_team.id:
                team.current_rank = new_loser_rank
                logging.info(f"[RANK SWAP]   {team.team_name}: #{loser_rank} → #{new_loser_rank} (LOSER)")
            elif team.current_rank > loser_rank:
                old_rank = team.current_rank
                team.current_rank = old_rank + 1
                logging.info(f"[RANK SWAP]   {team.team_name}: #{old_rank} → #{team.current_rank} (shifted down)")
                rank_changes['teams_affected'].append({
                    'team_name': team.team_name,
                    'old_rank': old_rank,
                    'new_rank': team.current_rank
                })

        rank_changes['winner']['new'] = new_winner_rank
        rank_changes['loser']['new'] = new_loser_rank

    db.session.commit()
    logging.info(f"[RANK SWAP] Rank swap completed successfully")

    ranks_after = {}
    for team in all_teams:
        ranks_after[team.current_rank] = team.team_name

    for rank in sorted(ranks_after.keys()):
        if rank <= max(winner_rank, loser_rank) + 2:
            logging.info(f"[RANK SWAP]   Rank #{rank}: {ranks_after[rank]}")

    return rank_changes


def verify_match_scores(match):
    """
    Verify that both teams submitted scores for the same match.
    Since scores are stored consistently (team_a_score_set1 is always Team A's games,
    team_b_score_set1 is always Team B's games), if both teams submitted, scores are verified.
    Returns True if scores exist and are valid, False if there's a dispute.
    """
    from datetime import datetime
    from utils import send_email_notification

    team_a = LadderTeam.query.get(match.team_a_id)
    team_b = LadderTeam.query.get(match.team_b_id)

    if not match.team_a_submitted or not match.team_b_submitted:
        return False

    # Both teams submitted scores - they are automatically consistent
    # because they're stored in the same fields regardless of submission order
    set1_valid = (match.team_a_score_set1 is not None and match.team_b_score_set1 is not None)
    set2_valid = (match.team_a_score_set2 is not None and match.team_b_score_set2 is not None)
    set3_valid = True
    
    if match.team_a_score_set3 is not None or match.team_b_score_set3 is not None:
        # Both teams must agree on whether set 3 exists
        set3_valid = (match.team_a_score_set3 is not None and match.team_b_score_set3 is not None)

    scores_match = set1_valid and set2_valid and set3_valid

    if scores_match:
        match.status = 'completed'
        match.completed_at = datetime.now()
        match.verified = True
        match.disputed = False
        
        # Mark the associated challenge as completed if it exists
        if match.challenge_id:
            challenge = LadderChallenge.query.get(match.challenge_id)
            if challenge:
                challenge.status = 'completed'

        team_a_sets_won = 0
        team_b_sets_won = 0
        team_a_games_total = 0
        team_b_games_total = 0

        sets = [
            (match.team_a_score_set1, match.team_b_score_set1),
            (match.team_a_score_set2, match.team_b_score_set2),
        ]
        if match.team_a_score_set3 is not None:
            sets.append((match.team_a_score_set3, match.team_b_score_set3))

        for team_a_games, team_b_games in sets:
            team_a_games_total += team_a_games
            team_b_games_total += team_b_games
            if team_a_games > team_b_games:
                team_a_sets_won += 1
            elif team_b_games > team_a_games:
                team_b_sets_won += 1

        match.sets_a = team_a_sets_won
        match.sets_b = team_b_sets_won
        match.games_a = team_a_games_total
        match.games_b = team_b_games_total

        if team_a_sets_won > team_b_sets_won:
            match.winner_id = team_a.id
        elif team_b_sets_won > team_a_sets_won:
            match.winner_id = team_b.id
        else:
            match.winner_id = None

        match.score_a = f"{match.team_a_score_set1}-{match.team_b_score_set1}"
        if match.team_a_score_set2 is not None:
            match.score_a += f", {match.team_a_score_set2}-{match.team_b_score_set2}"
        if match.team_a_score_set3 is not None:
            match.score_a += f", {match.team_a_score_set3}-{match.team_b_score_set3}"

        match.score_b = f"{match.team_b_score_set1}-{match.team_a_score_set1}"
        if match.team_b_score_set2 is not None:
            match.score_b += f", {match.team_b_score_set2}-{match.team_a_score_set2}"
        if match.team_b_score_set3 is not None:
            match.score_b += f", {match.team_b_score_set3}-{match.team_a_score_set3}"

        update_ladder_team_stats_from_match(match)

        rank_changes = None
        if match.winner_id:
            winner_team = team_a if match.winner_id == team_a.id else team_b
            loser_team = team_b if match.winner_id == team_a.id else team_a

            rank_changes = swap_ladder_ranks(winner_team, loser_team, match)

            match.winner_old_rank = rank_changes['winner']['old']
            match.winner_new_rank = rank_changes['winner']['new']
            match.loser_old_rank = rank_changes['loser']['old']
            match.loser_new_rank = rank_changes['loser']['new']

        db.session.commit()

        winner_name = team_a.team_name if match.winner_id == team_a.id else (team_b.team_name if match.winner_id == team_b.id else "Draw")

        rank_info_a = ""
        rank_info_b = ""

        if rank_changes:
            if match.winner_id == team_a.id:
                old_rank = rank_changes['winner']['old']
                new_rank = rank_changes['winner']['new']
                opponent_old = rank_changes['loser']['old']
                opponent_new = rank_changes['loser']['new']

                if new_rank < old_rank:
                    rank_info_a = f"\n🎯 RANK UPDATE: You moved UP from #{old_rank} to #{new_rank}! ⬆️\n   {team_b.team_name} dropped from #{opponent_old} to #{opponent_new}\n"
                elif new_rank > old_rank:
                    rank_info_a = f"\n📊 RANK UPDATE: Your rank changed from #{old_rank} to #{new_rank}\n"
                else:
                    rank_info_a = f"\n📊 RANK UPDATE: You remain at rank #{old_rank}\n"

                rank_info_b = f"\n📉 RANK UPDATE: You dropped from #{opponent_old} to #{opponent_new} ⬇️\n   {team_a.team_name} moved from #{old_rank} to #{new_rank}\n"
            else:
                old_rank = rank_changes['loser']['old']
                new_rank = rank_changes['loser']['new']
                opponent_old = rank_changes['winner']['old']
                opponent_new = rank_changes['winner']['new']

                rank_info_a = f"\n📉 RANK UPDATE: You dropped from #{old_rank} to #{new_rank} ⬇️\n   {team_b.team_name} moved from #{opponent_old} to #{opponent_new}\n"

                if opponent_new < opponent_old:
                    rank_info_b = f"\n🎯 RANK UPDATE: You moved UP from #{opponent_old} to #{opponent_new}! ⬆️\n   {team_a.team_name} dropped from #{old_rank} to #{new_rank}\n"
                elif opponent_new > opponent_old:
                    rank_info_b = f"\n📊 RANK UPDATE: Your rank changed from #{opponent_old} to #{opponent_new}\n"
                else:
                    rank_info_b = f"\n📊 RANK UPDATE: You remain at rank #{opponent_old}\n"

        team_a_message = f"""
Match Scores Verified!

Your match against {team_b.team_name} has been verified and recorded.

Final Score: {match.score_a}
Result: {"You Won! 🎉" if match.winner_id == team_a.id else ("You Lost" if match.winner_id == team_b.id else "Draw")}
{rank_info_a}
Both teams submitted matching scores. Your stats have been updated.

Manage your team: {request.url_root}ladder/my-team/{team_a.access_token}

Good game!
BD Padel Ladder Team
"""

        team_b_message = f"""
Match Scores Verified!

Your match against {team_a.team_name} has been verified and recorded.

Final Score: {match.score_b}
Result: {"You Won! 🎉" if match.winner_id == team_b.id else ("You Lost" if match.winner_id == team_a.id else "Draw")}
{rank_info_b}
Both teams submitted matching scores. Your stats have been updated.

Manage your team: {request.url_root}ladder/my-team/{team_b.access_token}

Good game!
BD Padel Ladder Team
"""

        if team_a.contact_preference_email:
            if team_a.player1_email:
                send_email_notification(team_a.player1_email, f"Match Verified - {team_a.team_name}", team_a_message)
            if team_a.player2_email and team_a.player2_email != team_a.player1_email:
                send_email_notification(team_a.player2_email, f"Match Verified - {team_a.team_name}", team_a_message)

        if team_b.contact_preference_email:
            if team_b.player1_email:
                send_email_notification(team_b.player1_email, f"Match Verified - {team_b.team_name}", team_b_message)
            if team_b.player2_email and team_b.player2_email != team_b.player1_email:
                send_email_notification(team_b.player2_email, f"Match Verified - {team_b.team_name}", team_b_message)

        return True
    else:
        match.status = 'disputed'
        match.disputed = True
        match.verified = False
        db.session.commit()

        dispute_message_a = f"""
Score Dispute Detected

There is a mismatch between the scores submitted by you and {team_b.team_name}.

Your submission:
- Set 1: {match.team_a_score_set1}-{match.team_b_score_set1}
- Set 2: {match.team_a_score_set2}-{match.team_b_score_set2}
{f"- Set 3: {match.team_a_score_set3}-{match.team_b_score_set3}" if match.team_a_score_set3 else ""}

{team_b.team_name}'s submission:
- Set 1: {match.team_b_score_set1}-{match.team_a_score_set1}
- Set 2: {match.team_b_score_set2}-{match.team_a_score_set2}
{f"- Set 3: {match.team_b_score_set3}-{match.team_a_score_set3}" if match.team_b_score_set3 else ""}

An administrator will review and resolve this dispute. You will be notified once it's resolved.

Manage your team: {request.url_root}ladder/my-team/{team_a.access_token}

BD Padel Ladder Team
"""

        dispute_message_b = f"""
Score Dispute Detected

There is a mismatch between the scores submitted by you and {team_a.team_name}.

Your submission:
- Set 1: {match.team_b_score_set1}-{match.team_a_score_set1}
- Set 2: {match.team_b_score_set2}-{match.team_a_score_set2}
{f"- Set 3: {match.team_b_score_set3}-{match.team_a_score_set3}" if match.team_b_score_set3 else ""}

{team_a.team_name}'s submission:
- Set 1: {match.team_a_score_set1}-{match.team_b_score_set1}
- Set 2: {match.team_a_score_set2}-{match.team_b_score_set2}
{f"- Set 3: {match.team_a_score_set3}-{match.team_b_score_set3}" if match.team_a_score_set3 else ""}

An administrator will review and resolve this dispute. You will be notified once it's resolved.

Manage your team: {request.url_root}ladder/my-team/{team_b.access_token}

BD Padel Ladder Team
"""

        if team_a.contact_preference_email:
            if team_a.player1_email:
                send_email_notification(team_a.player1_email, f"Score Dispute - {team_a.team_name}", dispute_message_a)
            if team_a.player2_email and team_a.player2_email != team_a.player1_email:
                send_email_notification(team_a.player2_email, f"Score Dispute - {team_a.team_name}", dispute_message_a)

        if team_b.contact_preference_email:
            if team_b.player1_email:
                send_email_notification(team_b.player1_email, f"Score Dispute - {team_b.team_name}", dispute_message_b)
            if team_b.player2_email and team_b.player2_email != team_b.player1_email:
                send_email_notification(team_b.player2_email, f"Score Dispute - {team_b.team_name}", dispute_message_b)

        return False


@app.route("/ladder/my-team/<token>", methods=["GET", "POST"])
def ladder_my_team(token):
    """Team-specific dashboard for ladder teams to manage matches, challenges, and holiday mode"""
    from datetime import datetime, timedelta

    # Verify access token and get team
    team = LadderTeam.query.filter_by(access_token=token).first_or_404()

    # Get ladder settings for grace period calculations
    settings = LadderSettings.query.first()
    if not settings:
        # Create default settings if none exist
        settings = LadderSettings(
            challenge_acceptance_hours=48,
            challenge_completion_days=7,
            max_challenge_rank_difference=3,
            acceptance_penalty_ranks=1,
            no_show_penalty_ranks=1,
            min_matches_per_month=2,
            inactivity_penalty_ranks=3,
            holiday_mode_grace_weeks=2,
            holiday_mode_weekly_penalty_ranks=1,
            free_agent_partner_selection_days=3
        )
        db.session.add(settings)
        db.session.commit()

    # Handle POST requests (placeholders for later implementation)
    if request.method == "POST":
        action = request.form.get("action")

        if action == "toggle_holiday":
            from utils import send_email_notification
            from datetime import datetime, timedelta

            now = datetime.now()

            if team.holiday_mode_active:
                team.holiday_mode_active = False
                team.holiday_mode_end = now

                db.session.commit()

                deactivation_message = f"""
Holiday Mode Deactivated

Welcome back to the ladder, {team.team_name}!

Your holiday mode has been deactivated and you can now participate in challenges again.

Team Dashboard: {request.url_root}ladder/my-team/{team.access_token}

Regards,
BD Padel Ladder Team
"""

                if team.contact_preference_email:
                    if team.player1_email:
                        send_email_notification(team.player1_email, f"Holiday Mode Deactivated - {team.team_name}", deactivation_message)
                    if team.player2_email and team.player2_email != team.player1_email:
                        send_email_notification(team.player2_email, f"Holiday Mode Deactivated - {team.team_name}", deactivation_message)

                flash("Holiday mode deactivated! Welcome back to the ladder.", "success")
                return redirect(url_for('ladder_my_team', token=token))
            else:
                active_challenges_sent = LadderChallenge.query.filter(
                    LadderChallenge.challenger_team_id == team.id,
                    LadderChallenge.status.in_(['pending_acceptance', 'accepted'])
                ).count()

                active_challenges_received = LadderChallenge.query.filter(
                    LadderChallenge.challenged_team_id == team.id,
                    LadderChallenge.status.in_(['pending_acceptance', 'accepted'])
                ).count()

                pending_matches = LadderMatch.query.filter(
                    db.or_(
                        LadderMatch.team_a_id == team.id,
                        LadderMatch.team_b_id == team.id
                    ),
                    LadderMatch.verified == False,
                    LadderMatch.status.in_(['pending', 'pending_opponent_score'])
                ).count()

                if active_challenges_sent > 0 or active_challenges_received > 0 or pending_matches > 0:
                    flash("Cannot activate holiday mode while you have active challenges or pending matches. Please complete or cancel them first.", "error")
                    return redirect(url_for('ladder_my_team', token=token))

                team.holiday_mode_active = True
                team.holiday_mode_start = now

                db.session.commit()

                grace_period_days = settings.holiday_mode_grace_weeks * 7

                activation_message = f"""
Holiday Mode Activated

{team.team_name}, your holiday mode has been successfully activated!

What this means:
- You have {grace_period_days} days ({settings.holiday_mode_grace_weeks} weeks) of grace period with no rank penalties
- You cannot be challenged by other teams during this time
- You cannot challenge other teams during this time
- After the grace period, you will be penalized {settings.holiday_mode_weekly_penalty_ranks} rank(s) per week
- You can deactivate holiday mode anytime through your team dashboard

Grace Period: {grace_period_days} days (until {(now + timedelta(days=grace_period_days)).strftime('%B %d, %Y')})

Team Dashboard: {request.url_root}ladder/my-team/{team.access_token}

Enjoy your break!

Regards,
BD Padel Ladder Team
"""

                if team.contact_preference_email:
                    if team.player1_email:
                        send_email_notification(team.player1_email, f"Holiday Mode Activated - {team.team_name}", activation_message)
                    if team.player2_email and team.player2_email != team.player1_email:
                        send_email_notification(team.player2_email, f"Holiday Mode Activated - {team.team_name}", activation_message)

                flash(f"Holiday mode activated! You have {grace_period_days} days of grace period before any penalties apply.", "success")
                return redirect(url_for('ladder_my_team', token=token))

        elif action == "submit_score":
            from utils import send_email_notification

            match_id = request.form.get("match_id")
            if not match_id:
                flash("Match ID is required", "error")
                return redirect(url_for('ladder_my_team', token=token))

            match = LadderMatch.query.get(match_id)
            if not match:
                flash("Match not found", "error")
                return redirect(url_for('ladder_my_team', token=token))

            if match.team_a_id != team.id and match.team_b_id != team.id:
                flash("You are not authorized to submit scores for this match", "error")
                return redirect(url_for('ladder_my_team', token=token))

            challenge = LadderChallenge.query.get(match.challenge_id)
            now = datetime.now()

            if challenge and challenge.completion_deadline:
                if now > challenge.completion_deadline:
                    team_a = LadderTeam.query.get(match.team_a_id)
                    team_b = LadderTeam.query.get(match.team_b_id)

                    if not match.team_a_submitted and not match.team_b_submitted:
                        apply_rank_penalty(team_a, 1, f"Failed to complete match against {team_b.team_name} before deadline")
                        apply_rank_penalty(team_b, 1, f"Failed to complete match against {team_a.team_name} before deadline")
                        flash(f"Match deadline has passed. Both teams have been penalized 1 rank.", "warning")

            try:
                set1_team = int(request.form.get("set1_team_score", 0))
                set1_opp = int(request.form.get("set1_opponent_score", 0))
                set2_team = int(request.form.get("set2_team_score", 0))
                set2_opp = int(request.form.get("set2_opponent_score", 0))

                set3_team_str = request.form.get("set3_team_score", "").strip()
                set3_opp_str = request.form.get("set3_opponent_score", "").strip()

                set3_team = int(set3_team_str) if set3_team_str else None
                set3_opp = int(set3_opp_str) if set3_opp_str else None

                if set1_team < 0 or set1_opp < 0 or set2_team < 0 or set2_opp < 0:
                    flash("Scores cannot be negative", "error")
                    return redirect(url_for('ladder_my_team', token=token))

                if (set3_team is not None and set3_team < 0) or (set3_opp is not None and set3_opp < 0):
                    flash("Scores cannot be negative", "error")
                    return redirect(url_for('ladder_my_team', token=token))

                if set1_team > 7 or set1_opp > 7 or set2_team > 7 or set2_opp > 7:
                    flash("Invalid score: Games in a set cannot exceed 7 in padel", "error")
                    return redirect(url_for('ladder_my_team', token=token))

                if (set3_team is not None and set3_team > 7) or (set3_opp is not None and set3_opp > 7):
                    flash("Invalid score: Games in a set cannot exceed 7 in padel", "error")
                    return redirect(url_for('ladder_my_team', token=token))

            except (ValueError, TypeError):
                flash("Invalid score format. Please enter valid numbers.", "error")
                return redirect(url_for('ladder_my_team', token=token))

            is_team_a = (match.team_a_id == team.id)

            if is_team_a:
                match.team_a_score_set1 = set1_team
                match.team_b_score_set1 = set1_opp
                match.team_a_score_set2 = set2_team
                match.team_b_score_set2 = set2_opp
                match.team_a_score_set3 = set3_team
                match.team_b_score_set3 = set3_opp
                match.team_a_submitted = True
                match.score_submitted_by_a = True
                if not match.first_submitter_id:
                    match.first_submitter_id = team.id
            else:
                match.team_b_score_set1 = set1_team
                match.team_a_score_set1 = set1_opp
                match.team_b_score_set2 = set2_team
                match.team_a_score_set2 = set2_opp
                match.team_b_score_set3 = set3_team
                match.team_a_score_set3 = set3_opp
                match.team_b_submitted = True
                match.score_submitted_by_b = True
                if not match.first_submitter_id:
                    match.first_submitter_id = team.id

            db.session.commit()

            opponent_team = LadderTeam.query.get(match.team_b_id if is_team_a else match.team_a_id)

            if match.team_a_submitted and match.team_b_submitted:
                # Both teams submitted - auto-verify the match
                verify_match_scores(match)
                flash("Your score has been submitted and the match is now complete!", "success")
            else:
                match.status = 'pending_opponent_score'
                db.session.commit()

                submission_message = f"""
Score Submitted

{team.team_name} has submitted their score for your match.

Match: {team.team_name} vs {opponent_team.team_name}

Please submit your score through your team dashboard as soon as possible.

Manage your team: {request.url_root}ladder/my-team/{opponent_team.access_token}

BD Padel Ladder Team
"""

                if opponent_team.contact_preference_email:
                    if opponent_team.player1_email:
                        send_email_notification(opponent_team.player1_email, f"Score Submission Waiting - {opponent_team.team_name}", submission_message)
                    if opponent_team.player2_email and opponent_team.player2_email != opponent_team.player1_email:
                        send_email_notification(opponent_team.player2_email, f"Score Submission Waiting - {opponent_team.team_name}", submission_message)

                flash("Your score has been submitted. Waiting for opponent to submit their score.", "success")

            return redirect(url_for('ladder_my_team', token=token))

        elif action == "accept_challenge":
            try:
                challenge_id = request.form.get("challenge_id")
                if not challenge_id:
                    flash("Challenge ID is required", "error")
                    return redirect(url_for('ladder_my_team', token=token))

                challenge = LadderChallenge.query.get(challenge_id)
                if not challenge:
                    flash("Challenge not found", "error")
                    return redirect(url_for('ladder_my_team', token=token))

                if challenge.challenged_team_id != team.id:
                    flash("You are not authorized to accept this challenge", "error")
                    return redirect(url_for('ladder_my_team', token=token))

                now = datetime.now()

                if now > challenge.acceptance_deadline:
                    apply_rank_penalty(team, settings.acceptance_penalty_ranks, 
                                     f"Failed to accept challenge from rank #{LadderTeam.query.get(challenge.challenger_team_id).current_rank} before deadline")
                    challenge.status = 'expired'
                    db.session.commit()
                    flash(f"Challenge acceptance deadline has passed. You have been penalized {settings.acceptance_penalty_ranks} rank(s).", "error")
                    return redirect(url_for('ladder_my_team', token=token))

                challenge.status = 'accepted'
                challenge.accepted_at = now
                challenge.completion_deadline = now + timedelta(days=settings.match_completion_days)

                match = LadderMatch(
                    team_a_id=challenge.challenger_team_id,
                    team_b_id=challenge.challenged_team_id,
                    challenge_id=challenge.id,
                    ladder_type=team.ladder_type,
                    created_at=now
                )
                db.session.add(match)
                db.session.add(challenge)  # Explicitly add challenge to ensure it's tracked
                db.session.commit()
                print(f"[DEBUG] Challenge {challenge_id} accepted. Status updated to: {challenge.status}")

                challenger_team = LadderTeam.query.get(challenge.challenger_team_id)
                challenged_team = team

                challenger_message = f"""Hello {challenger_team.team_name},

Challenge Accepted!

Great news! {challenged_team.team_name} has accepted your challenge!

Match Details:
- Opponent: {challenged_team.team_name} ({challenged_team.player1_name} & {challenged_team.player2_name})
- Their Rank: #{challenged_team.current_rank}
- Match Deadline: {challenge.completion_deadline.strftime('%B %d, %Y')}

You have {settings.match_completion_days} days to complete this match and submit scores.

Please coordinate with your opponent to schedule a time to play. You can contact them via:
- {challenged_team.player1_name}: {challenged_team.player1_phone}
- {challenged_team.player2_name}: {challenged_team.player2_phone}

After playing, both teams must submit scores through your team dashboard.

Good luck!

Regards,
BD Padel Ladder Team
"""

                challenged_message = f"""Hello {challenged_team.team_name},

Challenge Accepted!

You have successfully accepted the challenge from {challenger_team.team_name}!

Match Details:
- Opponent: {challenger_team.team_name} ({challenger_team.player1_name} & {challenger_team.player2_name})
- Their Rank: #{challenger_team.current_rank}
- Match Deadline: {challenge.completion_deadline.strftime('%B %d, %Y')}

You have {settings.match_completion_days} days to complete this match and submit scores.

Please coordinate with your opponent to schedule a time to play. You can contact them via:
- {challenger_team.player1_name}: {challenger_team.player1_phone}
- {challenger_team.player2_name}: {challenger_team.player2_phone}

After playing, both teams must submit scores through your team dashboard.

Good luck!

Regards,
BD Padel Ladder Team
"""

                from utils import send_email_notification

                if challenger_team.contact_preference_email:
                    if challenger_team.player1_email:
                        send_email_notification(challenger_team.player1_email, 
                                              f"Challenge Accepted - {challenger_team.team_name}", 
                                              challenger_message)
                    if challenger_team.player2_email and challenger_team.player2_email != challenger_team.player1_email:
                        send_email_notification(challenger_team.player2_email, 
                                              f"Challenge Accepted - {challenger_team.team_name}", 
                                              challenger_message)

                if challenged_team.contact_preference_email:
                    if challenged_team.player1_email:
                        send_email_notification(challenged_team.player1_email, 
                                              f"Challenge Accepted - {challenged_team.team_name}", 
                                              challenged_message)
                    if challenged_team.player2_email and challenged_team.player2_email != challenged_team.player1_email:
                        send_email_notification(challenged_team.player2_email, 
                                              f"Challenge Accepted - {challenged_team.team_name}", 
                                              challenged_message)

                flash(f"Challenge accepted! You have until {challenge.completion_deadline.strftime('%B %d, %Y')} to complete the match.", "success")
                return redirect(url_for('ladder_my_team', token=token))
            
            except Exception as e:
                db.session.rollback()
                print(f"[ERROR] Failed to accept challenge: {str(e)}")
                flash(f"Error accepting challenge: {str(e)}", "error")
                return redirect(url_for('ladder_my_team', token=token))

        elif action == "reject_challenge":
            challenge_id = request.form.get("challenge_id")
            if not challenge_id:
                flash("Challenge ID is required", "error")
                return redirect(url_for('ladder_my_team', token=token))

            challenge = LadderChallenge.query.get(challenge_id)
            if not challenge:
                flash("Challenge not found", "error")
                return redirect(url_for('ladder_my_team', token=token))

            if challenge.challenged_team_id != team.id:
                flash("You are not authorized to reject this challenge", "error")
                return redirect(url_for('ladder_my_team', token=token))

            now = datetime.now()

            if now > challenge.acceptance_deadline:
                apply_rank_penalty(team, settings.acceptance_penalty_ranks, 
                                 f"Failed to respond to challenge from rank #{LadderTeam.query.get(challenge.challenger_team_id).current_rank} before deadline")
                challenge.status = 'expired'
                db.session.commit()
                flash(f"Challenge acceptance deadline has passed. You have been penalized {settings.acceptance_penalty_ranks} rank(s) for late rejection.", "error")
                return redirect(url_for('ladder_my_team', token=token))

            challenge.status = 'rejected'
            db.session.commit()

            challenger_team = LadderTeam.query.get(challenge.challenger_team_id)
            challenged_team = team

            challenger_message = f"""Challenge Rejected

{challenged_team.team_name} has declined your challenge.

Challenge Details:
- Challenged Team: {challenged_team.team_name} ({challenged_team.player1_name} & {challenged_team.player2_name})
- Their Rank: #{challenged_team.current_rank}
- Status: Rejected

Both teams are now unlocked and available to send or receive new challenges.

You can challenge other teams by visiting the ladder rankings page.

Regards,
BD Padel Ladder Team
"""

            challenged_message = f"""Challenge Rejected

You have successfully rejected the challenge from {challenger_team.team_name}.

Challenge Details:
- Challenger Team: {challenger_team.team_name} ({challenger_team.player1_name} & {challenger_team.player2_name})
- Their Rank: #{challenger_team.current_rank}
- Status: Rejected

Both teams are now unlocked and available to send or receive new challenges.

Regards,
BD Padel Ladder Team
"""

            from utils import send_email_notification

            if challenger_team.contact_preference_email:
                if challenger_team.player1_email:
                    send_email_notification(challenger_team.player1_email, 
                                          f"Challenge Rejected - {challenger_team.team_name}", 
                                          challenger_message)
                if challenger_team.player2_email and challenger_team.player2_email != challenger_team.player1_email:
                    send_email_notification(challenger_team.player2_email, 
                                          f"Challenge Rejected - {challenger_team.team_name}", 
                                          challenger_message)

            if challenged_team.contact_preference_email:
                if challenged_team.player1_email:
                    send_email_notification(challenged_team.player1_email, 
                                          f"Challenge Rejected - {challenged_team.team_name}", 
                                          challenged_message)
                if challenged_team.player2_email and challenged_team.player2_email != challenged_team.player1_email:
                    send_email_notification(challenged_team.player2_email, 
                                          f"Challenge Rejected - {challenged_team.team_name}", 
                                          challenged_message)

            flash("Challenge rejected successfully. Both teams are now unlocked.", "success")
            return redirect(url_for('ladder_my_team', token=token))

        elif action == "cancel_challenge":
            from utils import send_email_notification
            
            challenge_id = request.form.get("challenge_id")
            if not challenge_id:
                flash("Challenge ID is required", "error")
                return redirect(url_for('ladder_my_team', token=token))

            challenge = LadderChallenge.query.get(challenge_id)
            if not challenge:
                flash("Challenge not found", "error")
                return redirect(url_for('ladder_my_team', token=token))

            if challenge.status not in ['accepted', 'pending_acceptance']:
                flash("Only pending or accepted challenges can be cancelled", "error")
                return redirect(url_for('ladder_my_team', token=token))

            # Verify the requesting team is either the challenger or challenged team
            is_challenger = challenge.challenger_team_id == team.id
            is_challenged = challenge.challenged_team_id == team.id
            
            if not is_challenger and not is_challenged:
                flash("You are not authorized to cancel this challenge", "error")
                return redirect(url_for('ladder_my_team', token=token))

            challenger_team = team
            challenged_team = LadderTeam.query.get(challenge.challenged_team_id)
            match = LadderMatch.query.filter_by(challenge_id=challenge.id).first()

            # Cancel the challenge
            challenge.status = 'cancelled'
            db.session.commit()

            # Delete the associated match if it exists and no scores have been submitted
            if match and not match.team_a_submitted and not match.team_b_submitted:
                db.session.delete(match)
                db.session.commit()

            challenger_message = f"""Challenge Cancelled

You have cancelled your challenge against {challenged_team.team_name}.

Challenge Details:
- Challenged Team: {challenged_team.team_name} ({challenged_team.player1_name} & {challenged_team.player2_name})
- Their Rank: #{challenged_team.current_rank}
- Status: Cancelled

Both teams are now unlocked and available to send or receive new challenges.

You can challenge other teams by visiting the ladder rankings page.

Regards,
BD Padel Ladder Team
"""

            challenged_message = f"""Challenge Cancelled

{challenger_team.team_name} has cancelled their challenge against you.

Challenge Details:
- Challenger Team: {challenger_team.team_name} ({challenger_team.player1_name} & {challenger_team.player2_name})
- Their Rank: #{challenger_team.current_rank}
- Status: Cancelled

Both teams are now unlocked and available to send or receive new challenges.

Regards,
BD Padel Ladder Team
"""

            if challenger_team.contact_preference_email:
                if challenger_team.player1_email:
                    send_email_notification(challenger_team.player1_email, 
                                          f"Challenge Cancelled - {challenger_team.team_name}", 
                                          challenger_message)
                if challenger_team.player2_email and challenger_team.player2_email != challenger_team.player1_email:
                    send_email_notification(challenger_team.player2_email, 
                                          f"Challenge Cancelled - {challenger_team.team_name}", 
                                          challenger_message)

            if challenged_team.contact_preference_email:
                if challenged_team.player1_email:
                    send_email_notification(challenged_team.player1_email, 
                                          f"Challenge Cancelled - {challenged_team.team_name}", 
                                          challenged_message)
                if challenged_team.player2_email and challenged_team.player2_email != challenged_team.player1_email:
                    send_email_notification(challenged_team.player2_email, 
                                          f"Challenge Cancelled - {challenged_team.team_name}", 
                                          challenged_message)

            flash("Challenge cancelled successfully. Both teams are now unlocked.", "success")
            return redirect(url_for('ladder_my_team', token=token))

        elif action == "report_no_show":
            from utils import send_email_notification

            match_id = request.form.get("match_id")
            if not match_id:
                flash("Match ID is required", "error")
                return redirect(url_for('ladder_my_team', token=token))

            match = LadderMatch.query.get(match_id)
            if not match:
                flash("Match not found", "error")
                return redirect(url_for('ladder_my_team', token=token))

            if match.team_a_id != team.id and match.team_b_id != team.id:
                flash("You are not authorized to report no-show for this match", "error")
                return redirect(url_for('ladder_my_team', token=token))

            if match.verified or match.status in ['completed', 'completed_no_show']:
                flash("Cannot report no-show for a completed match", "error")
                return redirect(url_for('ladder_my_team', token=token))

            if match.team_a_submitted and match.team_b_submitted:
                flash("Cannot report no-show when both teams have submitted scores", "error")
                return redirect(url_for('ladder_my_team', token=token))

            if match.reported_no_show_team_id:
                flash("A no-show report has already been filed for this match", "error")
                return redirect(url_for('ladder_my_team', token=token))

            challenge = LadderChallenge.query.get(match.challenge_id)
            now = datetime.now()

            if challenge and challenge.completion_deadline:
                if now <= challenge.completion_deadline:
                    deadline_str = challenge.completion_deadline.strftime('%B %d, %Y at %I:%M %p')
                    flash(f"Cannot report no-show before match completion deadline ({deadline_str})", "error")
                    return redirect(url_for('ladder_my_team', token=token))

            opponent_id = match.team_b_id if match.team_a_id == team.id else match.team_a_id
            opponent_team = LadderTeam.query.get(opponent_id)

            if not opponent_team:
                flash("Opponent team not found", "error")
                return redirect(url_for('ladder_my_team', token=token))

            match.reported_no_show_team_id = opponent_id
            match.reported_by_team_id = team.id
            match.no_show_report_date = now
            match.status = 'no_show_reported'

            db.session.commit()

            reporter_message = f"""
No-Show Report Submitted

{team.team_name}, your no-show report has been successfully submitted.

Match Details:
- Your Team: {team.team_name}
- Opponent Team: {opponent_team.team_name}
- Reported No-Show Team: {opponent_team.team_name}
- Report Date: {now.strftime('%B %d, %Y at %I:%M %p')}

An administrator will review your report shortly and take appropriate action. You will be notified once the review is complete.

If the no-show is verified:
- You will be awarded the match win
- Your opponent will receive a {settings.no_show_penalty_ranks} rank penalty

Team Dashboard: {request.url_root}ladder/my-team/{team.access_token}

Regards,
BD Padel Ladder Team
"""

            reported_team_message = f"""
No-Show Report - Immediate Action Required

{opponent_team.team_name}, you have been reported as a no-show for your match.

Match Details:
- Your Team: {opponent_team.team_name}
- Opponent Team: {team.team_name}
- Report Date: {now.strftime('%B %d, %Y at %I:%M %p')}

If this report is incorrect, please contact the administrator IMMEDIATELY by replying to this email with evidence that you:
1. Attempted to schedule the match
2. Were present at the agreed time and location
3. Have communication records with your opponent

If the no-show is verified by admin:
- Match will be awarded to {team.team_name}
- Your team will be penalized {settings.no_show_penalty_ranks} rank(s)
- Match will be marked as completed with no-show status

Team Dashboard: {request.url_root}ladder/my-team/{opponent_team.access_token}

IMPORTANT: Respond within 24 hours to dispute this report.

Regards,
BD Padel Ladder Team
"""

            admin_email = os.environ.get("ADMIN_EMAIL")
            admin_message = f"""
No-Show Report Requires Review

A no-show report has been submitted and requires admin review.

Report Details:
- Match ID: {match.id}
- Reporter Team: {team.team_name} (Rank #{team.current_rank})
  - Players: {team.player1_name} & {team.player2_name}
  - Contact: {team.player1_phone}
- Reported Team: {opponent_team.team_name} (Rank #{opponent_team.current_rank})
  - Players: {opponent_team.player1_name} & {opponent_team.player2_name}
  - Contact: {opponent_team.player1_phone}
- Report Date: {now.strftime('%B %d, %Y at %I:%M %p')}
- Match Completion Deadline: {challenge.completion_deadline.strftime('%B %d, %Y at %I:%M %p') if challenge and challenge.completion_deadline else 'N/A'}

Action Required:
1. Review communication between both teams
2. Verify if reported team was genuinely absent
3. Check if there were legitimate reasons for absence
4. Approve or reject the no-show report in admin panel

If Approved:
- {team.team_name} will be awarded the match win
- {opponent_team.team_name} will receive -{settings.no_show_penalty_ranks} rank penalty
- Match status will be updated to 'completed_no_show'

If Rejected:
- Both teams will be notified
- Match remains pending for score submission

Admin Panel: {request.url_root}admin

Regards,
BD Padel Ladder System
"""

            if team.contact_preference_email:
                if team.player1_email:
                    send_email_notification(team.player1_email, 
                                          f"No-Show Report Submitted - {team.team_name}", 
                                          reporter_message)
                if team.player2_email and team.player2_email != team.player1_email:
                    send_email_notification(team.player2_email, 
                                          f"No-Show Report Submitted - {team.team_name}", 
                                          reporter_message)

            if opponent_team.contact_preference_email:
                if opponent_team.player1_email:
                    send_email_notification(opponent_team.player1_email, 
                                          f"URGENT: No-Show Report Filed Against {opponent_team.team_name}", 
                                          reported_team_message)
                if opponent_team.player2_email and opponent_team.player2_email != opponent_team.player1_email:
                    send_email_notification(opponent_team.player2_email, 
                                          f"URGENT: No-Show Report Filed Against {opponent_team.team_name}", 
                                          reported_team_message)

            if admin_email:
                send_email_notification(admin_email, 
                                      f"No-Show Report Review Required - Match #{match.id}", 
                                      admin_message)

            flash(f"No-show report submitted for {opponent_team.team_name}. An administrator will review your report shortly.", "success")
            return redirect(url_for('ladder_my_team', token=token))

    # Query active challenges (sent and received)
    # Exclude challenges with matches that have scores submitted (matches in progress)
    challenges_sent = LadderChallenge.query.filter(
        LadderChallenge.challenger_team_id == team.id,
        LadderChallenge.status.in_(['pending_acceptance', 'accepted'])
    ).order_by(LadderChallenge.created_at.desc()).all()

    challenges_received = LadderChallenge.query.filter(
        LadderChallenge.challenged_team_id == team.id,
        LadderChallenge.status.in_(['pending_acceptance', 'accepted'])
    ).order_by(LadderChallenge.created_at.desc()).all()

    # Get opponent team info for challenges
    challenge_details_sent = []
    for challenge in challenges_sent:
        # Skip if the match for this challenge is in progress (scores have been submitted)
        match = LadderMatch.query.filter_by(challenge_id=challenge.id).first()
        if match and (match.team_a_submitted or match.team_b_submitted):
            continue  # Match is in progress, don't show challenge as active
        
        opponent = LadderTeam.query.get(challenge.challenged_team_id)
        if opponent:
            challenge_details_sent.append({
                'challenge': challenge,
                'opponent': opponent,
                'is_challenger': True
            })

    challenge_details_received = []
    now = datetime.now()
    for challenge in challenges_received:
        # Skip if the match for this challenge is in progress (scores have been submitted)
        match = LadderMatch.query.filter_by(challenge_id=challenge.id).first()
        if match and (match.team_a_submitted or match.team_b_submitted):
            continue  # Match is in progress, don't show challenge as active
        
        opponent = LadderTeam.query.get(challenge.challenger_team_id)
        if opponent:
            # Only calculate deadline info for pending_acceptance challenges
            # Accepted challenges don't have an acceptance deadline to worry about
            hours_until_deadline = 0
            is_deadline_approaching = False
            is_past_deadline = False
            
            if challenge.status == 'pending_acceptance':
                hours_until_deadline = (challenge.acceptance_deadline - now).total_seconds() / 3600
                is_deadline_approaching = hours_until_deadline < 24 and hours_until_deadline > 0
                is_past_deadline = hours_until_deadline <= 0

            challenge_details_received.append({
                'challenge': challenge,
                'opponent': opponent,
                'is_challenger': False,
                'hours_until_deadline': max(0, hours_until_deadline),
                'is_deadline_approaching': is_deadline_approaching,
                'is_past_deadline': is_past_deadline
            })

    # Query ladder matches for this team
    matches = LadderMatch.query.filter(
        db.or_(
            LadderMatch.team_a_id == team.id,
            LadderMatch.team_b_id == team.id
        )
    ).order_by(LadderMatch.created_at.desc()).all()

    # Separate pending and completed matches
    pending_matches = []
    completed_matches = []
    seen_opponents = {}  # Track opponent pairs to avoid duplicates

    for match in matches:
        opponent_id = match.team_b_id if match.team_a_id == team.id else match.team_a_id
        opponent = LadderTeam.query.get(opponent_id)
        challenge = LadderChallenge.query.get(match.challenge_id)

        is_team_a = match.team_a_id == team.id

        is_past_deadline = False
        if challenge and challenge.completion_deadline:
            is_past_deadline = now > challenge.completion_deadline

        match_detail = {
            'match': match,
            'opponent': opponent,
            'challenge': challenge,
            'is_team_a': is_team_a,
            'team_score': match.score_a if is_team_a else match.score_b,
            'opponent_score': match.score_b if is_team_a else match.score_a,
            'team_submitted': match.score_submitted_by_a if is_team_a else match.score_submitted_by_b,
            'opponent_submitted': match.score_submitted_by_b if is_team_a else match.score_submitted_by_a,
            'is_past_deadline': is_past_deadline,
        }

        if match.verified:
            completed_matches.append(match_detail)
        else:
            # Skip matches from completed challenges (duplicate/stale matches)
            if challenge and challenge.status == 'completed':
                continue
            
            # Deduplicate: only add the most recent match for each opponent pair
            opponent_key = opponent_id
            if opponent_key not in seen_opponents:
                seen_opponents[opponent_key] = True
                # Check if no-show report is pending admin review
                if match.status == 'no_show_reported':
                    match_detail['no_show_pending_review'] = True
                pending_matches.append(match_detail)

    # Calculate holiday mode grace period info using helper function
    holiday_info = calculate_holiday_status(team, settings)

    # Check if team is locked (in active challenge)
    is_locked = any(c['challenge'].status in ['pending_acceptance', 'accepted'] 
                    for c in challenge_details_sent + challenge_details_received)

    # Determine team status
    if is_locked:
        team_status = 'locked'
        status_color = 'orange'
        status_message = 'In Active Challenge'
    elif team.holiday_mode_active:
        team_status = 'holiday'
        status_color = 'blue'
        status_message = 'Holiday Mode'
    else:
        team_status = 'available'
        status_color = 'green'
        status_message = 'Available'

    # Calculate display rank (sequential position in ladder for this team's type/gender)
    all_teams_in_ladder = LadderTeam.query.filter_by(
        ladder_type=team.ladder_type,
        gender=team.gender
    ).order_by(LadderTeam.current_rank.asc()).all()
    
    # Map team IDs to their actual sequential rank (1..N) based on current sort
    team_id_to_seq_rank = {t.id: idx + 1 for idx, t in enumerate(all_teams_in_ladder)}
    team_display_rank = team_id_to_seq_rank.get(team.id)

    # Get teams that can be challenged (3 ranks above, expandable if teams are on holiday)
    challengeable_teams = []
    if not is_locked and not team.holiday_mode_active:
        max_rank_diff = settings.max_challenge_rank_difference if settings else 3
        
        if team_display_rank:
            # Find up to 3 available slots above me
            target_teams_data = []
            curr_target_idx = team_display_rank - 2  # -1 for 0-indexed, then -1 for team above
            
            # We'll look further up if we hit holiday teams
            while len(target_teams_data) < max_rank_diff and curr_target_idx >= 0:
                potential_t = all_teams_in_ladder[curr_target_idx]
                
                is_t_locked = LadderChallenge.query.filter(
                    db.or_(
                        LadderChallenge.challenger_team_id == potential_t.id,
                        LadderChallenge.challenged_team_id == potential_t.id
                    ),
                    LadderChallenge.status.in_(['pending_acceptance', 'accepted'])
                ).first() is not None
                
                if potential_t.holiday_mode_active and not is_t_locked:
                    # Skip this rank, look one higher
                    curr_target_idx -= 1
                    continue
                
                # This rank is valid (either available or locked but visible)
                target_teams_data.append({
                    'team': potential_t,
                    'is_locked': is_t_locked,
                    'is_holiday': potential_t.holiday_mode_active,
                    'display_rank': curr_target_idx + 1
                })
                curr_target_idx -= 1

            challengeable_teams = target_teams_data

    return render_template("ladder/my_team.html",
                         team=team,
                         team_display_rank=team_display_rank,
                         challenges_sent=challenge_details_sent,
                         challenges_received=challenge_details_received,
                         pending_matches=pending_matches,
                         completed_matches=completed_matches,
                         holiday_info=holiday_info,
                         settings=settings,
                         is_locked=is_locked,
                         team_status=team_status,
                         status_color=status_color,
                         status_message=status_message,
                         challengeable_teams=challengeable_teams)

@app.route("/ladder/login", methods=["GET", "POST"])
def ladder_login():
    """Team login for ladder system - allows teams to challenge others"""
    if request.method == "POST":
        access_token = request.form.get("access_token", "").strip()

        if not access_token:
            flash("Please enter your access token", "error")
            return redirect(url_for('ladder_login'))

        team = LadderTeam.query.filter_by(access_token=access_token).first()

        if not team:
            flash("Invalid access token. Please check your registration email for the correct token.", "error")
            return redirect(url_for('ladder_login'))

        session['ladder_team_id'] = team.id
        session['ladder_team_token'] = access_token
        flash(f"Welcome back, {team.team_name}!", "success")

        # Redirect based on the team's actual gender/ladder_type
        if team.gender == 'men' or team.ladder_type == 'men':
            return redirect(url_for('ladder_men'))
        else:
            return redirect(url_for('ladder_women'))

    return render_template("ladder/login.html")

@app.route("/ladder/logout")
def ladder_logout():
    """Logout from ladder team session"""
    team_id = session.get('ladder_team_id')
    if team_id:
        team = LadderTeam.query.get(team_id)
        if team:
            flash(f"Goodbye, {team.team_name}!", "info")

    session.pop('ladder_team_id', None)
    session.pop('ladder_team_token', None)
    return redirect(url_for('index'))

@app.route("/ladder/challenge/create", methods=["POST"])
def ladder_challenge_create():
    """Create a new ladder challenge from one team to another"""
    from datetime import datetime, timedelta
    from utils import send_email_notification

    # Try to get challenger from session first, then from token parameter
    challenger_id = session.get('ladder_team_id')
    challenger_token = request.form.get('token')
    
    if not challenger_id and not challenger_token:
        flash("Please log in to challenge other teams", "error")
        return redirect(url_for('ladder_login'))
    
    # If token is provided, get challenger from token
    if challenger_token and not challenger_id:
        challenger = LadderTeam.query.filter_by(access_token=challenger_token).first()
        if not challenger:
            flash("Invalid team token", "error")
            return redirect(url_for('ladder_login'))
        challenger_id = challenger.id
    elif challenger_id:
        challenger = LadderTeam.query.get(challenger_id)
        if not challenger:
            flash("Challenger team not found", "error")
            return redirect(url_for('ladder_login'))

    challenged_id = request.form.get('challenged_team_id', type=int)

    if not challenged_id:
        flash("Invalid challenge request", "error")
        return redirect(url_for('index'))

    challenged = LadderTeam.query.get(challenged_id)

    if not challenger or not challenged:
        flash("One or both teams not found", "error")
        return redirect(url_for('index'))

    settings = LadderSettings.query.first()
    if not settings:
        settings = LadderSettings(
            challenge_acceptance_hours=48,
            challenge_completion_days=7,
            max_challenge_rank_difference=3
        )
        db.session.add(settings)
        db.session.commit()

    # Prevent cross-gender challenges
    if challenger.ladder_type != challenged.ladder_type:
        flash("You can only challenge teams in your own ladder", "error")
        redirect_token = challenger_token or session.get('ladder_team_token')
        return redirect(url_for('ladder_my_team', token=redirect_token))

    if challenger.gender != challenged.gender:
        flash(f"You cannot challenge teams from a different gender category. You are in the {challenger.gender.title()}'s division.", "error")
        redirect_token = challenger_token or session.get('ladder_team_token')
        return redirect(url_for('ladder_my_team', token=redirect_token))

    if challenger.holiday_mode_active:
        flash("You cannot challenge while in holiday mode", "error")
        return redirect(url_for('ladder_men' if challenger.ladder_type == 'men' else 'ladder_women'))

    if challenged.holiday_mode_active:
        flash("You cannot challenge a team that is in holiday mode", "error")
        return redirect(url_for('ladder_men' if challenger.ladder_type == 'men' else 'ladder_women'))

    active_challenge_challenger = LadderChallenge.query.filter(
        db.or_(
            LadderChallenge.challenger_team_id == challenger_id,
            LadderChallenge.challenged_team_id == challenger_id
        ),
        LadderChallenge.status.in_(['pending_acceptance', 'accepted'])
    ).first()

    if active_challenge_challenger:
        flash("You already have an active challenge. Complete it before creating a new one.", "error")
        return redirect(url_for('ladder_men' if challenger.ladder_type == 'men' else 'ladder_women'))

    active_challenge_challenged = LadderChallenge.query.filter(
        db.or_(
            LadderChallenge.challenger_team_id == challenged_id,
            LadderChallenge.challenged_team_id == challenged_id
        ),
        LadderChallenge.status.in_(['pending_acceptance', 'accepted'])
    ).first()

    if active_challenge_challenged:
        flash(f"{challenged.team_name} is already in an active challenge", "error")
        return redirect(url_for('ladder_men' if challenger.ladder_type == 'men' else 'ladder_women'))

    rank_diff = challenger.current_rank - challenged.current_rank
    if rank_diff <= 0:
        flash("You can only challenge teams ranked above you", "error")
        return redirect(url_for('ladder_men' if challenger.ladder_type == 'men' else 'ladder_women'))

    if rank_diff > settings.max_challenge_rank_difference:
        flash(f"You can only challenge teams within {settings.max_challenge_rank_difference} ranks above you", "error")
        return redirect(url_for('ladder_men' if challenger.ladder_type == 'men' else 'ladder_women'))

    acceptance_deadline = datetime.utcnow() + timedelta(hours=settings.challenge_acceptance_hours)

    new_challenge = LadderChallenge(
        challenger_team_id=challenger_id,
        challenged_team_id=challenged_id,
        ladder_type=challenger.ladder_type,
        status='pending_acceptance',
        acceptance_deadline=acceptance_deadline,
        created_at=datetime.utcnow()
    )

    db.session.add(new_challenge)
    db.session.commit()

    challenger_email_body = f"""Hello {challenger.team_name},

Your challenge to {challenged.team_name} has been sent successfully!

They have {settings.challenge_acceptance_hours} hours ({settings.challenge_acceptance_hours // 24} days) to accept your challenge.

If they don't accept within the deadline, they will receive a -{settings.acceptance_penalty_ranks} rank penalty.

You'll receive an email notification once they accept. Good luck!

---
Padel Ladder League
"""

    challenged_email_body = f"""Hello {challenged.team_name},

You have been challenged by {challenger.team_name} (Rank #{challenger.current_rank})!

⚠️ IMPORTANT: You have {settings.challenge_acceptance_hours} hours ({settings.challenge_acceptance_hours // 24} days) to accept this challenge.

If you don't accept by {acceptance_deadline.strftime('%B %d, %Y at %I:%M %p UTC')}, you will receive a -{settings.acceptance_penalty_ranks} rank penalty.

Accept the challenge here:
{request.url_root}ladder/my-team/{challenged.access_token}

Good luck!

---
Padel Ladder League
"""

    if challenger.contact_preference_email and challenger.player1_email:
        send_email_notification(
            challenger.player1_email,
            f"Challenge Sent to {challenged.team_name}",
            challenger_email_body
        )

    if challenged.contact_preference_email and challenged.player1_email:
        send_email_notification(
            challenged.player1_email,
            f"⚠️ Challenge from {challenger.team_name} - Action Required!",
            challenged_email_body
        )

    flash(f"Challenge sent to {challenged.team_name}! They have {settings.challenge_acceptance_hours // 24} days to accept.", "success")
    redirect_token = challenger_token or session.get('ladder_team_token')
    if redirect_token:
        return redirect(url_for('ladder_my_team', token=redirect_token))
    else:
        return redirect(url_for('ladder_men' if challenger.ladder_type == 'men' else 'ladder_women'))

@app.route("/leaderboard")
def leaderboard():
    """
    Leaderboard with proper padel league ranking:
    1. Status (active teams first, inactive teams last)
    2. Points (3 for win, 1 for draw, 0 for loss)
    3. Sets difference
    4. Games difference
    5. Wins
    6. Team name (alphabetical)
    """
    teams = Team.query.order_by(
        Team.status.asc(),  # 'active' comes before 'inactive' alphabetically
        Team.points.desc(),
        (Team.sets_for - Team.sets_against).desc(),
        (Team.games_for - Team.games_against).desc(),
        Team.wins.desc(),
        Team.team_name
    ).all()

    # Check playoff qualification status
    settings = LeagueSettings.query.first()
    qualified_team_ids = []
    team_seeds = {}

    if settings and settings.qualified_team_ids:
        import json
        try:
            qualified_team_ids = json.loads(settings.qualified_team_ids)
            # Create a seed mapping (team_id -> seed number)
            for seed, team_id in enumerate(qualified_team_ids, start=1):
                team_seeds[team_id] = seed
        except:
            pass

    return render_template("leaderboard.html", teams=teams, team_seeds=team_seeds, playoff_phase=settings.current_phase if settings else "swiss")

@app.route("/players")
def player_leaderboard():
    """
    Player leaderboard organized by team ranking
    Teams are ranked by: Status > Points > Sets Diff > Games Diff > Wins > Team Name
    Players within each team are sorted by: Points > Wins > Matches Played > Sets Diff > Games Diff
    Includes all players with stats including substitutes and free agents
    """
    # Get teams in ranked order (same as team leaderboard)
    teams = Team.query.order_by(
        Team.status.asc(),  # 'active' comes before 'inactive' alphabetically
        Team.points.desc(),
        (Team.sets_for - Team.sets_against).desc(),
        (Team.games_for - Team.games_against).desc(),
        Team.wins.desc(),
        Team.team_name
    ).all()
    
    # Build players list grouped by team rank
    players_by_team = []
    processed_player_ids = set()
    
    for team_rank, team in enumerate(teams, start=1):
        # Get all players from this team who have stats
        team_players = Player.query.filter(
            Player.current_team_id == team.id,
            db.or_(
                (Player.wins > 0) | 
                (Player.losses > 0) | 
                (Player.draws > 0) |
                (Player.matches_played > 0)
            )
        ).order_by(
            Player.points.desc(),
            Player.wins.desc(),
            Player.matches_played.desc(),
            (Player.sets_for - Player.sets_against).desc(),
            (Player.games_for - Player.games_against).desc(),
            Player.name
        ).all()
        
        # Add substitute indicator and team info
        for player in team_players:
            player.is_substitute = db.session.query(Substitute).filter_by(player_id=player.id).first() is not None
            player.team_rank = team_rank
            player.team_name = team.team_name
            processed_player_ids.add(player.id)
        
        players_by_team.extend(team_players)
    
    # Also include players with stats who aren't currently on any ranked team (substitutes, free agents)
    other_players = Player.query.filter(
        Player.id.notin_(processed_player_ids),
        db.or_(
            (Player.wins > 0) | 
            (Player.losses > 0) | 
            (Player.draws > 0) |
            (Player.matches_played > 0)
        )
    ).order_by(
        Player.points.desc(),
        Player.wins.desc(),
        Player.matches_played.desc(),
        (Player.sets_for - Player.sets_against).desc(),
        (Player.games_for - Player.games_against).desc(),
        Player.name
    ).all()
    
    for player in other_players:
        player.is_substitute = db.session.query(Substitute).filter_by(player_id=player.id).first() is not None
        player.team_rank = None
        player.team_name = None
    
    players_by_team.extend(other_players)
    
    return render_template("player_leaderboard.html", players=players_by_team)

@app.route("/player/<int:player_id>")
def player_profile(player_id: int):
    """Individual player profile with detailed stats and match history"""
    player = Player.query.get_or_404(player_id)

    # Get all matches this player participated in
    matches = Match.query.filter(
        db.or_(
            Match.team_a_player1_id == player_id,
            Match.team_a_player2_id == player_id,
            Match.team_b_player1_id == player_id,
            Match.team_b_player2_id == player_id
        ),
        Match.status == "completed"
    ).order_by(Match.round.desc()).all()

    # Enrich matches with details
    match_details = []
    for match in matches:
        team_a = Team.query.get(match.team_a_id)
        team_b = Team.query.get(match.team_b_id)

        # Determine which team the player was on
        on_team_a = (match.team_a_player1_id == player_id or match.team_a_player2_id == player_id)
        player_team = team_a if on_team_a else team_b
        opponent_team = team_b if on_team_a else team_a

        # Determine partner
        if on_team_a:
            partner_id = match.team_a_player2_id if match.team_a_player1_id == player_id else match.team_a_player1_id
        else:
            partner_id = match.team_b_player2_id if match.team_b_player1_id == player_id else match.team_b_player1_id

        partner = Player.query.get(partner_id) if partner_id else None

        # Determine result
        if on_team_a:
            won = match.winner_id == match.team_a_id
            score = match.score_a
        else:
            won = match.winner_id == match.team_b_id
            score = match.score_b

        match_details.append({
            'match': match,
            'player_team': player_team,
            'opponent_team': opponent_team,
            'partner': partner,
            'won': won,
            'score': score
        })

    # Get current team
    current_team = Team.query.get(player.current_team_id) if player.current_team_id else None

    # Get substitute info if player is a substitute
    substitute_info = Substitute.query.filter_by(player_id=player.id).first()
    substitute_team = Team.query.get(substitute_info.team_id) if substitute_info else None
    replaced_player_name = None
    
    if substitute_info and substitute_team:
        # Get the replaced player name from team roster
        # (Don't use match record because it's already been updated with substitute ID)
        if substitute_info.replaces_player_number == 1:
            replaced_player_name = substitute_team.player1_name
        else:  # replaces_player_number == 2
            replaced_player_name = substitute_team.player2_name

    # Calculate additional stats
    recent_form = []
    for detail in match_details[:5]:  # Last 5 matches
        if detail['won']:
            recent_form.append('W')
        elif detail['match'].winner_id is None:
            recent_form.append('D')
        else:
            recent_form.append('L')

    return render_template(
        "player_profile.html",
        player=player,
        current_team=current_team,
        match_details=match_details,
        recent_form=recent_form,
        substitute_info=substitute_info,
        substitute_team=substitute_team,
        replaced_player_name=replaced_player_name
    )

@app.route("/my-matches/<token>")
def my_matches(token):
    """Secure token-based access to team's matches and opponent contact info"""
    team = Team.query.filter_by(access_token=token).first_or_404()

    # Get all matches for this team
    matches = Match.query.filter(
        (Match.team_a_id == team.id) | (Match.team_b_id == team.id)
    ).order_by(Match.round.desc(), Match.id.desc()).all()

    # Enrich matches with opponent info and round dates
    match_details = []
    for match in matches:
        opponent_id = match.team_b_id if match.team_a_id == team.id else match.team_a_id
        opponent = Team.query.get(opponent_id) if opponent_id else None

        # Add round date range
        match.round_dates = get_round_date_range(match)
        
        # Check if match has been rescheduled
        is_rescheduled = Reschedule.query.filter_by(match_id=match.id).first() is not None

        match_details.append({
            'match': match,
            'opponent': opponent,
            'is_team_a': match.team_a_id == team.id,
            'is_rescheduled': is_rescheduled
        })

    # Sort matches: Active/scheduled first (by round descending), then completed by round
    # This ensures current round appears at top, followed by completed matches
    scheduled = [m for m in match_details if m['match'].status != 'completed']
    completed = [m for m in match_details if m['match'].status == 'completed']
    
    # Sort scheduled by round descending (current round first)
    scheduled.sort(key=lambda x: x['match'].round if x['match'].round else 0, reverse=True)
    
    # Sort completed by round descending (newest completed first)
    completed.sort(key=lambda x: x['match'].round if x['match'].round else 0, reverse=True)
    
    # Combine: Scheduled first, then completed
    sorted_match_details = scheduled + completed

    return render_template(
        "my_matches.html",
        team=team,
        match_details=sorted_match_details
    )

@app.route("/submit-booking/<token>", methods=["POST"])
def submit_booking(token):
    """Handle booking submission from team's secure page"""
    from datetime import datetime
    from utils import send_email_notification

    team = Team.query.filter_by(access_token=token).first_or_404()

    try:
        data = request.get_json()
        match_id = int(data.get("match_id"))
        booking_date = data.get("date")  # YYYY-MM-DD
        booking_time = data.get("time")  # HH:MM

        if not all([match_id, booking_date, booking_time]):
            return {"success": False, "message": "Missing required fields"}, 400

        # Find the match
        match = Match.query.get(match_id)
        if not match:
            return {"success": False, "message": "Match not found"}, 404

        # Verify team is part of this match
        if match.team_a_id != team.id and match.team_b_id != team.id:
            return {"success": False, "message": "Unauthorized"}, 403

        # Parse datetime
        datetime_str = f"{booking_date} {booking_time}"
        match_datetime = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")

        # Check if it's in the past
        if match_datetime < datetime.now():
            return {"success": False, "message": "Booking time cannot be in the past"}, 400

        # CRITICAL: Validate booking date is within round date range
        if match.round:
            if match.round_deadline:
                # Range is (deadline - 6 days) to deadline
                round_end_date = match.round_deadline.date()
                from datetime import timedelta
                round_start_date = round_end_date - timedelta(days=6)
            else:
                round_start_date = get_round_start_date(match.round)
                if round_start_date:
                    from datetime import timedelta, date
                    # Special handling for Round 5: extend end date to Dec 27
                    if match.round == 5:
                        round_end_date = date(2025, 12, 27)
                    else:
                        round_end_date = round_start_date + timedelta(days=6)  # Sunday
                else:
                    round_end_date = None
            
            if round_start_date and round_end_date:
                booking_date_obj = datetime.strptime(booking_date, "%Y-%m-%d").date()

                if booking_date_obj < round_start_date or booking_date_obj > round_end_date:
                    round_dates = get_round_date_range(match)
                    return {
                        "success": False,
                        "message": f"Booking date must be within round dates ({round_dates}). For dates outside this range, please use the Reschedule Request feature."
                    }, 400

        # Get opponent
        opponent_id = match.team_b_id if match.team_a_id == team.id else match.team_a_id
        opponent = Team.query.get(opponent_id)

        # Check if there's an existing booking or if this is a change to confirmed booking
        if match.booking_details:
            # Parse existing booking
            try:
                existing_datetime_str = match.booking_details.split("Court assigned on arrival")[0].strip()

                # If booking was already confirmed and someone is proposing a new time
                if match.booking_confirmed:
                    # Reset confirmation and store new proposal
                    match.booking_confirmed = False
                    match.booking_requested_by = team.id
                    formatted_datetime = match_datetime.strftime("%A, %B %d at %I:%M %p")
                    match.booking_details = f"{formatted_datetime}\nCourt assigned on arrival\nWaiting for {opponent.team_name} to confirm..."
                    match.match_datetime = match_datetime
                    db.session.commit()

                    # Notify opponent about the change
                    base_url = "https://goeclectic.xyz"
                    notification_body = f"""Hi!

{team.team_name} has proposed a CHANGE to your confirmed match booking:

NEW Proposed Time: {formatted_datetime}
Court: Assigned on arrival

Please log in to confirm or propose a different time:
{base_url}/my-matches/{opponent.access_token}

- BD Padel League
"""
                    if opponent.player1_email:
                        send_email_notification(opponent.player1_email, "Match Booking Change Proposed", notification_body)
                    if opponent.player2_email:
                        send_email_notification(opponent.player2_email, "Match Booking Change Proposed", notification_body)

                    return {
                        "success": True,
                        "message": f"Booking change submitted! Waiting for {opponent.team_name} to confirm the new time.",
                        "confirmed": False,
                        "booking_details": match.booking_details
                    }
            except:
                pass

        # Store this team's booking (waiting for opponent confirmation)
        formatted_datetime = match_datetime.strftime("%A, %B %d at %I:%M %p")
        match.booking_details = f"{formatted_datetime}\nCourt assigned on arrival\nWaiting for {opponent.team_name} to confirm..."
        match.booking_requested_by = team.id
        match.match_datetime = match_datetime  # Store for potential confirmation
        db.session.commit()

        # Notify opponent
        base_url = "https://goeclectic.xyz"
        notification_body = f"""Hi!

{team.team_name} has proposed a match booking:

Date & Time: {formatted_datetime}
Court: Assigned on arrival

Please log in to confirm or propose a different time:
{base_url}/my-matches/{opponent.access_token}

- BD Padel League
"""
        if opponent.player1_email:
            send_email_notification(opponent.player1_email, "Match Booking Proposed", notification_body)
        if opponent.player2_email:
            send_email_notification(opponent.player2_email, "Match Booking Proposed", notification_body)

        return {
            "success": True,
            "message": f"Booking submitted! Waiting for {opponent.team_name} to confirm.",
            "confirmed": False,
            "booking_details": match.booking_details
        }

    except Exception as e:
        print(f"[ERROR] Booking submission failed: {e}")
        return {"success": False, "message": str(e)}, 500

@app.route("/confirm-booking/<token>", methods=["POST"])
def confirm_booking(token):
    """Handle booking confirmation from team's secure page (no re-entry needed)"""
    from datetime import datetime
    from utils import send_email_notification

    team = Team.query.filter_by(access_token=token).first_or_404()

    try:
        data = request.get_json()
        match_id = int(data.get("match_id"))

        if not match_id:
            return {"success": False, "message": "Match ID required"}, 400

        # Find the match
        match = Match.query.get(match_id)
        if not match:
            return {"success": False, "message": "Match not found"}, 404

        # Verify team is part of this match
        if match.team_a_id != team.id and match.team_b_id != team.id:
            return {"success": False, "message": "Unauthorized"}, 403

        # Check if there's already a booking proposal
        if not match.booking_details or match.booking_confirmed:
            return {"success": False, "message": "No booking proposal to confirm"}, 400

        # Parse the existing booking to extract datetime
        try:
            # Extract the datetime from the booking details
            # Format: "Wednesday, October 22 at 06:30 PM\nCourt assigned on arrival\nWaiting for DUMMY_Lightning Bolts to confirm..."
            booking_lines = match.booking_details.split('\n')
            datetime_str = booking_lines[0].strip()  # "Wednesday, October 22 at 06:30 PM"

            # Convert to datetime object - parse without year, then replace with current year
            parsed_datetime = datetime.strptime(datetime_str, "%A, %B %d at %I:%M %p")
            match_datetime = parsed_datetime.replace(year=datetime.now().year)

            # Get opponent
            opponent_id = match.team_b_id if match.team_a_id == team.id else match.team_a_id
            opponent = Team.query.get(opponent_id)

            # Confirm the booking
            match.match_datetime = match_datetime
            match.match_date = datetime_str
            match.court = "Court assigned on arrival"
            match.booking_confirmed = True
            match.booking_details = f"{datetime_str}\nCourt assigned on arrival\n✓ Confirmed by both teams"
            db.session.commit()

            # Send confirmation emails to both teams
            confirmation_body = f"""Hi!

Your match booking has been confirmed by both teams:

Match: {team.team_name} vs {opponent.team_name}
Date & Time: {match.match_date}
Court: Assigned on arrival

See you on the court! 🎾

- BD Padel League
"""
            # Send to confirming team
            if team.player1_email:
                send_email_notification(team.player1_email, "Match Booking Confirmed", confirmation_body)
            if team.player2_email:
                send_email_notification(team.player2_email, "Match Booking Confirmed", confirmation_body)

            # Send to proposing team
            if opponent.player1_email:
                send_email_notification(opponent.player1_email, "Match Booking Confirmed", confirmation_body)
            if opponent.player2_email:
                send_email_notification(opponent.player2_email, "Match Booking Confirmed", confirmation_body)

            return {
                "success": True,
                "message": "Booking confirmed! Both teams have agreed on the schedule.",
                "confirmed": True,
                "booking_details": match.booking_details
            }

        except Exception as parse_error:
            print(f"[ERROR] Failed to parse existing booking: {parse_error}")
            return {"success": False, "message": "Invalid booking format. Please contact admin."}, 400

    except Exception as e:
        print(f"[ERROR] Booking confirmation failed: {e}")
        return {"success": False, "message": str(e)}, 500

def update_bracket_winners(match):
    """
    Automatically advance the winner of a knockout match to their next designated bracket slot.
    QF1, QF2 -> SF1
    QF3, QF4 -> SF2
    SF1, SF2 -> F1
    """
    if not match.winner_id or match.phase == 'final' or match.round >= 8:
        return

    next_slot = None
    is_team_a = True

    if match.bracket_slot == 'QF1':
        next_slot = 'SF1'
        is_team_a = True
    elif match.bracket_slot == 'QF2':
        next_slot = 'SF1'
        is_team_a = False
    elif match.bracket_slot == 'QF3':
        next_slot = 'SF2'
        is_team_a = True
    elif match.bracket_slot == 'QF4':
        next_slot = 'SF2'
        is_team_a = False
    elif match.bracket_slot == 'SF1':
        next_slot = 'F1'
        is_team_a = True
    elif match.bracket_slot == 'SF2':
        next_slot = 'F1'
        is_team_a = False

    if next_slot:
        # Find the match in the next round with this slot
        next_match = Match.query.filter_by(bracket_slot=next_slot).first()
        if next_match:
            if is_team_a:
                next_match.team_a_id = match.winner_id
            else:
                next_match.team_b_id = match.winner_id
            db.session.commit()
            print(f"[BRACKET] Advanced team {match.winner_id} to {next_slot} ({'Team A' if is_team_a else 'Team B'})")

@app.route("/confirm-score/<token>", methods=["POST"])
def confirm_score(token):
    """Handle score confirmation from team's secure page (no re-entry needed)"""
    from utils import calculate_match_result, normalize_score_string, send_email_notification

    team = Team.query.filter_by(access_token=token).first_or_404()

    try:
        data = request.get_json()
        match_id = int(data.get("match_id"))
        action = data.get("action")  # "confirm" or "dispute"

        if not match_id or not action:
            return {"success": False, "message": "Match ID and action required"}, 400

        # Find the match
        match = Match.query.get(match_id)
        if not match:
            return {"success": False, "message": "Match not found"}, 404

        # Verify team is part of this match
        if match.team_a_id != team.id and match.team_b_id != team.id:
            return {"success": False, "message": "Unauthorized"}, 403

        # Check if there's a score to confirm
        if not match.score_submission_a and not match.score_submission_b:
            return {"success": False, "message": "No score submitted to confirm"}, 400

        # Get opponent
        opponent_id = match.team_b_id if match.team_a_id == team.id else match.team_a_id
        opponent = Team.query.get(opponent_id)

        # Determine which team submitted the score
        if match.team_a_id == team.id:
            # Team A is confirming Team B's score
            submitted_score = match.score_submission_b
            submitted_by_team = opponent
        else:
            # Team B is confirming Team A's score
            submitted_score = match.score_submission_a
            submitted_by_team = opponent

        if action == "confirm":
            # Confirm the score - both teams agree
            # Determine canonical A/B perspective score strings
            try:
                if match.team_a_id == team.id:
                    # Opponent (Team B) submitted their perspective
                    score_b_str = submitted_score
                    score_a_str = invert_score_string(submitted_score)
                else:
                    # Opponent (Team A) submitted their perspective
                    score_a_str = submitted_score
                    score_b_str = invert_score_string(submitted_score)

                # Calculate match result from Team A and Team B perspectives
                sets_a, sets_b, games_a, games_b, winner_code = calculate_match_result(
                    score_a_str, score_b_str
                )

                # Update match with confirmed score (canonical A/B)
                match.score_a = score_a_str
                match.score_b = score_b_str
                match.sets_a = sets_a
                match.sets_b = sets_b
                match.games_a = games_a
                match.games_b = games_b
                match.winner_id = match.team_a_id if winner_code == 'a' else (
                    match.team_b_id if winner_code == 'b' else None
                )
                match.verified = True
                match.status = "completed"
                match.stats_calculated = False  # Trigger stats recalculation

                # Update team statistics
                update_team_stats_from_match(match)

                # NEW: Update knockout bracket winners
                if match.round >= 6:
                    update_bracket_winners(match)

                db.session.commit()

                # Send confirmation emails to both teams
                winner_name = (
                    Team.query.get(match.winner_id).team_name if match.winner_id else "Draw"
                )
                confirmation_body = f"""Hi!

Match score has been confirmed by both teams:

Match: {team.team_name} vs {opponent.team_name}
Score: {match.score_a} - {match.score_b}
Winner: {winner_name}

The score has been verified and recorded in the system.

- BD Padel League
"""
                # Send to confirming team
                if team.player1_email:
                    send_email_notification(team.player1_email, "Match Score Confirmed", confirmation_body)
                if team.player2_email:
                    send_email_notification(team.player2_email, "Match Score Confirmed", confirmation_body)

                # Send to opponent
                if opponent.player1_email:
                    send_email_notification(opponent.player1_email, "Match Score Confirmed", confirmation_body)
                if opponent.player2_email:
                    send_email_notification(opponent.player2_email, "Match Score Confirmed", confirmation_body)

                return {
                    "success": True,
                    "message": "Score confirmed! Match result has been verified and recorded.",
                    "verified": True,
                    "winner": winner_name,
                    "score": f"{match.score_a} - {match.score_b}"
                }

            except Exception as parse_error:
                print(f"[ERROR] Failed to parse score for confirmation: {parse_error}")
                return {"success": False, "message": "Invalid score format. Please contact admin."}, 400

        elif action == "dispute":
            # Dispute the score - escalate to admin
            # Clear the disputed score submission
            if match.team_a_id == team.id:
                match.score_submission_b = None
                match.score_submitted_by_b = False
            else:
                match.score_submission_a = None
                match.score_submitted_by_a = False
            db.session.commit()

            # Send dispute notification to both teams
            dispute_body = f"""Hi!

The match score has been disputed and requires admin review:

Match: {team.team_name} vs {opponent.team_name}
Disputed Score: {submitted_score}
Disputed by: {team.team_name}

The admin will contact both teams to resolve this dispute.

- BD Padel League
"""
            # Send to disputing team
            if team.player1_email:
                send_email_notification(team.player1_email, "Score Dispute Submitted", dispute_body)
            if team.player2_email:
                send_email_notification(team.player2_email, "Score Dispute Submitted", dispute_body)

            # Send to opponent
            if opponent.player1_email:
                send_email_notification(opponent.player1_email, "Score Dispute - Admin Review Required", dispute_body)
            if opponent.player2_email:
                send_email_notification(opponent.player2_email, "Score Dispute - Admin Review Required", dispute_body)

            return {
                "success": True,
                "message": "Score dispute submitted! Admin will review and contact both teams to resolve.",
                "disputed": True
            }

        else:
            return {"success": False, "message": "Invalid action. Use 'confirm' or 'dispute'."}, 400

    except Exception as e:
        print(f"[ERROR] Score confirmation failed: {e}")
        return {"success": False, "message": str(e)}, 500

@app.route("/submit-score/<token>", methods=["POST"])
def submit_score(token):
    """Handle score submission from team's secure page"""
    from utils import calculate_match_result, normalize_score_string, send_email_notification

    team = Team.query.filter_by(access_token=token).first_or_404()

    try:
        data = request.get_json()
        match_id = int(data.get("match_id"))
        set1 = data.get("set1", "").strip()
        set2 = data.get("set2", "").strip()
        set3 = data.get("set3", "").strip()

        if not all([match_id, set1, set2]):
            return {"success": False, "message": "At least 2 sets are required"}, 400

        # Find the match
        match = Match.query.get(match_id)
        if not match:
            return {"success": False, "message": "Match not found"}, 404

        # Verify team is part of this match
        is_team_a = match.team_a_id == team.id
        is_team_b = match.team_b_id == team.id

        if not is_team_a and not is_team_b:
            return {"success": False, "message": "Unauthorized"}, 403

        # Build score string
        score_parts = [set1, set2]
        if set3:
            score_parts.append(set3)
        submitted_score = ", ".join(score_parts)

        # Normalize the score
        try:
            normalized_score = normalize_score_string(submitted_score)
        except ValueError as e:
            return {"success": False, "message": f"Invalid score format: {e}"}, 400

        # Get opponent
        opponent_id = match.team_b_id if is_team_a else match.team_a_id
        opponent = Team.query.get(opponent_id)

        # Store submission
        if is_team_a:
            match.score_submission_a = normalized_score
            match.score_submitted_by_a = True
        else:
            match.score_submission_b = normalized_score
            match.score_submitted_by_b = True

        # IMPORTANT: Commit the first submission so it persists to database
        db.session.commit()

        # Check if opponent also submitted
        if match.score_submitted_by_a and match.score_submitted_by_b:
            # Both teams submitted, check if they match
            if match.score_submission_a == match.score_submission_b:
                # Scores match! Verify the match
                team_a = Team.query.get(match.team_a_id)
                team_b = Team.query.get(match.team_b_id)

                match.score_a = match.score_submission_a
                match.score_b = match.score_submission_a  # Same score
                match.verified = True
                match.status = "completed"

                # Calculate match result
                result = calculate_match_result(match.score_a)
                match.sets_a = result["sets_won"]
                match.sets_b = result["sets_lost"]
                match.games_a = result["games_won"]
                match.games_b = result["games_lost"]

                if result["sets_won"] > result["sets_lost"]:
                    match.winner_id = match.team_a_id
                elif result["sets_lost"] > result["sets_won"]:
                    match.winner_id = match.team_b_id
                else:
                    match.winner_id = None  # Draw

                # Populate player IDs for this match (who actually played)
                player1_a = Player.query.filter_by(phone=team_a.player1_phone).first()
                player2_a = Player.query.filter_by(phone=team_a.player2_phone).first()
                player1_b = Player.query.filter_by(phone=team_b.player1_phone).first()
                player2_b = Player.query.filter_by(phone=team_b.player2_phone).first()

                if player1_a:
                    match.team_a_player1_id = player1_a.id
                if player2_a:
                    match.team_a_player2_id = player2_a.id
                if player1_b:
                    match.team_b_player1_id = player1_b.id
                if player2_b:
                    match.team_b_player2_id = player2_b.id

                # Update all stats (team + player) using centralized function
                from utils import verify_match_and_calculate_stats
                verify_match_and_calculate_stats(match, team_a, team_b, db.session)

                # NEW: Update knockout bracket winners
                if match.round >= 6:
                    update_bracket_winners(match)

                db.session.commit()

                # Send confirmation emails
                winner_name = team_a.team_name if match.winner_id == team_a.id else (team_b.team_name if match.winner_id == team_b.id else "Draw")
                confirmation_body = f"""Hi!

Match score has been verified by both teams:

{team_a.team_name} vs {team_b.team_name}
Score: {match.score_a}
Winner: {winner_name}

Check the leaderboard for updated standings!

- BD Padel League
"""
                for t in [team_a, team_b]:
                    if t.player1_email:
                        send_email_notification(t.player1_email, "Match Score Verified", confirmation_body)
                    if t.player2_email:
                        send_email_notification(t.player2_email, "Match Score Verified", confirmation_body)

                return {
                    "success": True,
                    "message": "Score verified! Match complete.",
                    "verified": True,
                    "winner": winner_name,
                    "score": match.score_a
                }
            else:
                # Scores don't match - need admin intervention
                db.session.commit()
                return {
                    "success": True,
                    "message": "Score submitted but doesn't match opponent's submission. Admin will review.",
                    "verified": False,
                    "your_score": normalized_score,
                    "opponent_score": match.score_submission_a if is_team_b else match.score_submission_b
                }
        else:
            # First team to submit
            db.session.commit()

            # Notify opponent
            base_url = "https://goeclectic.xyz"
            notification_body = f"""Hi!

{team.team_name} has submitted their match score:

Score: {normalized_score}

Please log in to confirm the score:
{base_url}/my-matches/{opponent.access_token}

- BD Padel League
"""
            if opponent.player1_email:
                send_email_notification(opponent.player1_email, "Match Score Submitted", notification_body)
            if opponent.player2_email:
                send_email_notification(opponent.player2_email, "Match Score Submitted", notification_body)

            return {
                "success": True,
                "message": f"Score submitted! Waiting for {opponent.team_name} to confirm.",
                "verified": False,
                "your_score": normalized_score
            }

    except Exception as e:
        print(f"[ERROR] Score submission failed: {e}")
        return {"success": False, "message": str(e)}, 500

@app.route("/submit-reschedule/<token>", methods=["POST"])
def submit_reschedule(token):
    """Handle reschedule request from team's secure page"""
    team = Team.query.filter_by(access_token=token).first_or_404()

    try:
        data = request.get_json()
        match_id = int(data.get("match_id"))
        date = data.get("date", "").strip()
        time = data.get("time", "").strip()

        if not all([match_id, date, time]):
            return {"success": False, "message": "Match ID, date, and time are required"}, 400

        # Find the match
        match = Match.query.get(match_id)
        if not match:
            return {"success": False, "message": "Match not found"}, 404

        # Verify team is part of this match
        if match.team_a_id != team.id and match.team_b_id != team.id:
            return {"success": False, "message": "Unauthorized"}, 403

        # Check reschedule limit (max 3 per team)
        if team.reschedules_used >= 3:
            return {
                "success": False,
                "message": "Your team has already used all 3 reschedules. No more subs allowed in league stage."
            }, 400

        # NEW: Disable reschedules for knockout rounds (Round 6+)
        if match.round >= 6:
            return {
                "success": False,
                "message": "Rescheduling is not permitted during knockout rounds (Round 6+)."
            }, 400

        # Check if we've reached the round reschedule limit
        pending_reschedules = get_pending_reschedules()
        max_per_round = get_max_reschedules_per_round()

        if len(pending_reschedules) >= max_per_round:
            return {
                "success": False,
                "message": f"Maximum reschedule limit reached for this round ({max_per_round} reschedules). Please wait for admin to process pending requests or contact admin for special approval."
            }, 400

        # Validate reschedule request based on round deadline
        from datetime import datetime, timedelta
        today = datetime.now().date()
        selected_date = datetime.strptime(date, "%Y-%m-%d").date()
        
        # Determine the round deadline - use match.round_deadline if set, otherwise calculate
        if match.round_deadline:
            round_deadline_date = match.round_deadline.date()
            # Reschedule request cutoff: 2 days before round deadline
            reschedule_cutoff = round_deadline_date - timedelta(days=2)
            # Makeup match deadline: 3 days after round deadline
            makeup_deadline = round_deadline_date + timedelta(days=3)
        else:
            # Fallback to legacy week-based logic
            current_weekday = today.weekday()  # 0 = Monday, 6 = Sunday
            if current_weekday == 0:
                days_until_next_monday = 7
            else:
                days_until_next_monday = (7 - current_weekday) % 7
                if days_until_next_monday == 0:
                    days_until_next_monday = 7
            next_monday = today + timedelta(days=days_until_next_monday)
            round_deadline_date = next_monday + timedelta(days=6)  # Sunday
            reschedule_cutoff = round_deadline_date - timedelta(days=2)
            makeup_deadline = round_deadline_date + timedelta(days=3)
        
        # Validate reschedule request is before cutoff
        if today > reschedule_cutoff:
            return {
                "success": False,
                "message": f"Reschedule requests must be submitted by {reschedule_cutoff.strftime('%B %d, %Y')} (2 days before round deadline)"
            }, 400
        
        # Validate selected date is between now and makeup deadline
        if selected_date < today or selected_date > makeup_deadline:
            return {
                "success": False,
                "message": f"Reschedule date must be between {today.strftime('%Y-%m-%d')} and {makeup_deadline.strftime('%Y-%m-%d')} (makeup deadline)"
            }, 400

        # Check if this is a valid round for reschedule (1 round limitation)
        current_round = match.round
        if current_round is None:
            return {"success": False, "message": "Cannot reschedule: Invalid round number"}, 400

        # Validate this is not a reschedule of a reschedule (Swiss format protection)
        existing_reschedules = Reschedule.query.filter_by(
            match_id=match_id,
            requester_team_id=team.id,
            status="pending"
        ).count()

        if existing_reschedules > 0:
            return {
                "success": False,
                "message": "You already have a pending reschedule request for this match. Please wait for admin approval."
            }, 400

        # Create reschedule request
        from datetime import datetime
        proposed_time_formatted = f"{date} at {time}"
        req = Reschedule(
            match_id=match_id,
            requester_team_id=team.id,
            proposed_time=proposed_time_formatted,
            status="pending",
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        db.session.add(req)
        db.session.commit()

        # Use the dynamically calculated makeup deadline for notification
        deadline_text = f"⚠️ MAKEUP MATCH DEADLINE: {makeup_deadline.strftime('%A, %B %d')} 23:59"

        # Send email notifications to both teams
        from utils import send_email_notification
        opponent_id = match.team_b_id if match.team_a_id == team.id else match.team_a_id
        opponent = Team.query.get(opponent_id)

        # Send admin notification
        admin_email = os.environ.get("ADMIN_EMAIL")
        if admin_email:
            admin_body = f"""🔔 NEW RESCHEDULE REQUEST

Team Requesting: {team.team_name}
Opponent Team: {opponent.team_name if opponent else 'Unknown'}

Match Details:
- Round: {match.round}
- Current Match Date: {match.match_datetime.strftime('%a, %b %d, %Y %I:%M %p') if match.match_datetime else 'Not scheduled'}
- Proposed Date/Time: {proposed_time_formatted}
- Makeup Match Deadline: {makeup_deadline.strftime('%A, %B %d')} 23:59

Team Reschedules Used: {team.reschedules_used}/2

Status: PENDING APPROVAL

Access the admin panel to approve or deny this request.

- BD Padel League
"""
            send_email_notification(admin_email, f"🔔 Reschedule Request - Round {match.round} - {team.team_name}", admin_body)

        # Email to requester team
        requester_body = f"""Hi {team.team_name},

Your reschedule request has been submitted and is awaiting admin approval.

Match Details:
- Round: {match.round}
- Opponent: {opponent.team_name if opponent else 'Unknown'}
- Proposed Time: {proposed_time_formatted}
- Deadline: {deadline_text}

Admin will review your request. Both teams will be notified once approved/denied.

Team Reschedules Used: {team.reschedules_used}/2

- BD Padel League
"""
        if team.player1_email:
            send_email_notification(team.player1_email, f"Reschedule Request Submitted - Round {match.round}", requester_body)
        if team.player2_email:
            send_email_notification(team.player2_email, f"Reschedule Request Submitted - Round {match.round}", requester_body)

        # Email to opponent team
        if opponent:
            opponent_body = f"""Hi {opponent.team_name},

{team.team_name} has submitted a reschedule request for your match.

Match Details:
- Round: {match.round}
- Proposed Time: {proposed_time_formatted}
- Deadline: {deadline_text}

Admin will review this request. You'll be notified once approved/denied.

- BD Padel League
"""
            if opponent.player1_email:
                send_email_notification(opponent.player1_email, f"Reschedule Request - Round {match.round}", opponent_body)
            if opponent.player2_email:
                send_email_notification(opponent.player2_email, f"Reschedule Request - Round {match.round}", opponent_body)

        return {
            "success": True,
            "message": f"✅ Reschedule submitted for {proposed_time_formatted}! {deadline_text}. If not completed by deadline, automatic walkover to opponent. You'll play 2 matches in the following week (makeup + regular round match). ({team.reschedules_used}/2 used)",
            "reschedules_used": team.reschedules_used,
            "reschedules_limit": 2
        }

    except Exception as e:
        print(f"[ERROR] Reschedule request failed: {e}")
        return {"success": False, "message": str(e)}, 500

@app.route("/get-previous-substitutes/<token>", methods=["GET"])
def get_previous_substitutes(token):
    """Get list of previously requested substitutes for a team (only pending/approved)"""
    team = Team.query.filter_by(access_token=token).first_or_404()
    
    # Get unique substitute names from this team's approved substitute requests
    subs = db.session.query(Substitute).filter(
        Substitute.team_id == team.id,
        Substitute.status.in_(["pending", "approved"])
    ).distinct(Substitute.name).all()
    
    result = [{"id": s.id, "name": s.name, "phone": s.phone, "email": s.email} for s in subs]
    return result

@app.route("/submit-substitute/<token>", methods=["POST"])
def submit_substitute(token):
    """Handle substitute request from team's secure page"""
    team = Team.query.filter_by(access_token=token).first_or_404()

    try:
        data = request.get_json()
        match_id = int(data.get("match_id"))
        sub_name = data.get("sub_name", "").strip()
        sub_phone = data.get("sub_phone", "").strip()
        sub_email = data.get("sub_email", "").strip()
        replaces_player = data.get("replaces_player", "").strip()

        if not all([match_id, sub_name, sub_phone, sub_email, replaces_player]):
            return {"success": False, "message": "All fields including which player is being replaced are required"}, 400

        # Find the match
        match = Match.query.get(match_id)
        if not match:
            return {"success": False, "message": "Match not found"}, 404

        # Verify team is part of this match
        if match.team_a_id != team.id and match.team_b_id != team.id:
            return {"success": False, "message": "Unauthorized"}, 403

        # NEW: Disable substitutions for knockout rounds (Round 6+)
        if match.round >= 6:
            return {
                "success": False,
                "message": "Substitution requests are not permitted during knockout rounds (Round 6+)."
            }, 400

        # Check substitute limit (max 2 per team in league stage)
        if team.subs_used >= 2:
            return {
                "success": False,
                "message": "Your team has already used all 2 substitutes. No more subs allowed in league stage."
            }, 400

        # Create substitute request
        from datetime import datetime

        # Get the replaced player's name
        replaced_player_name = team.player1_name if replaces_player == "1" else team.player2_name

        s = Substitute(
            team_id=team.id,
            match_id=match_id,
            name=sub_name,
            phone=sub_phone,
            email=sub_email,
            replaces_player_number=int(replaces_player),
            status="pending",
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        db.session.add(s)
        db.session.commit()

        # Send notifications to all parties
        from utils import send_email_notification

        # Send admin notification
        admin_email = os.environ.get("ADMIN_EMAIL")
        if admin_email:
            opponent_id = match.team_b_id if match.team_a_id == team.id else match.team_a_id
            opponent = Team.query.get(opponent_id)
            admin_body = f"""🔔 NEW SUBSTITUTE REQUEST

Team Requesting: {team.team_name}
Opponent Team: {opponent.team_name if opponent else 'Unknown'}

Match Details:
- Round: {match.round}
- Match Date: {match.match_datetime.strftime('%a, %b %d, %Y %I:%M %p') if match.match_datetime else 'Not scheduled'}

Substitute Information:
- Name: {sub_name}
- Phone: {sub_phone}
- Email: {sub_email}
- Replacing: {replaced_player_name} (Player {replaces_player})

Team Substitutes Used: {team.subs_used}/2

Status: PENDING APPROVAL

Access the admin panel to approve or deny this request.

- BD Padel League
"""
            send_email_notification(admin_email, f"🔔 Substitute Request - Round {match.round} - {team.team_name}", admin_body)

        # Email subject and body
        subject = f"Substitute Request Submitted - Round {match.round}"

        # Email to Player 1
        if team.player1_email:
            body1 = f"""Hello {team.player1_name},

Your substitute request has been submitted and is awaiting admin approval.

Match Details:
- Round: {match.round}
- Team: {team.team_name}
- Substitute: {sub_name} ({sub_email})
- Replacing: {replaced_player_name}

Admin will review and approve/deny your request soon. You will receive a confirmation email once processed.

Thank you!
Padel League Hub"""
            send_email_notification(team.player1_email, subject, body1)

        # Email to Player 2
        if team.player2_email:
            body2 = f"""Hello {team.player2_name},

Your teammate has submitted a substitute request which is awaiting admin approval.

Match Details:
- Round: {match.round}
- Team: {team.team_name}
- Substitute: {sub_name} ({sub_email})
- Replacing: {replaced_player_name}

Admin will review and approve/deny the request soon. You will receive a confirmation email once processed.

Thank you!
Padel League Hub"""
            send_email_notification(team.player2_email, subject, body2)

        # Email to Substitute
        sub_body = f"""Hello {sub_name},

You have been requested as a substitute player and the request is awaiting admin approval.

Match Details:
- Round: {match.round}
- Team: {team.team_name}
- Team Players: {team.player1_name} & {team.player2_name}
- You will replace: {replaced_player_name}

Admin will review and approve/deny the request soon. You will receive a confirmation email once processed.

Thank you for participating!
Padel League Hub"""
        send_email_notification(sub_email, subject, sub_body)

        return {
            "success": True,
            "message": f"✅ Substitute request submitted! Email notifications sent to all parties. Admin will review your request. ({team.subs_used}/2 substitutes used)",
            "subs_used": team.subs_used,
            "subs_limit": 2
        }

    except Exception as e:
        print(f"[ERROR] Substitute request failed: {e}")
        return {"success": False, "message": str(e)}, 500

@app.route("/team/<int:team_id>")
def team_profile(team_id: int):
    team = Team.query.get_or_404(team_id)
    matches = Match.query.filter(
        (Match.team_a_id == team_id) | (Match.team_b_id == team_id)
    ).order_by(Match.round.desc(), Match.id.desc()).all()

    recent = []
    for m in matches:
        if m.status == "completed":
            if m.winner_id is None:
                recent.append("D")
            elif m.winner_id == team_id:
                recent.append("W")
            else:
                recent.append("L")
        if len(recent) >= 5:
            break

    # Get all teams for opponent lookup
    teams = Team.query.all()

    return render_template(
        "team.html",
        team=team,
        matches=matches,
        recent_form=recent,
        teams=teams,
    )

@app.route("/stats")
def league_stats():
    """League statistics page with various rankings and streaks"""
    from datetime import datetime, timedelta

    teams = Team.query.all()

    # Calculate streaks for each team
    team_streaks = {}
    for team in teams:
        matches = Match.query.filter(
            (Match.team_a_id == team.id) | (Match.team_b_id == team.id)
        ).filter(Match.status == "completed").order_by(Match.round.desc(), Match.id.desc()).all()

        current_streak = 0
        streak_type = None

        for match in matches:
            if match.winner_id == team.id:
                if streak_type == "W" or streak_type is None:
                    current_streak += 1
                    streak_type = "W"
                else:
                    break
            elif match.winner_id is None:  # Draw
                if streak_type == "D" or streak_type is None:
                    current_streak += 1
                    streak_type = "D"
                else:
                    break
            else:  # Loss
                if streak_type == "L" or streak_type is None:
                    current_streak += 1
                    streak_type = "L"
                else:
                    break

        team_streaks[team.id] = {
            'streak': current_streak,
            'type': streak_type or "N/A"
        }

    # Sort teams by different criteria
    teams_by_points = sorted(teams, key=lambda t: t.points, reverse=True)
    teams_by_sets_diff = sorted(teams, key=lambda t: t.sets_for - t.sets_against, reverse=True)
    teams_by_games_diff = sorted(teams, key=lambda t: t.games_for - t.games_against, reverse=True)
    teams_by_wins = sorted(teams, key=lambda t: t.wins, reverse=True)
    teams_by_streak = sorted(teams, key=lambda t: team_streaks[t.id]['streak'], reverse=True)

    # Ladder Statistics
    ladder_men_teams = LadderTeam.query.filter_by(ladder_type='men').count()
    ladder_women_teams = LadderTeam.query.filter_by(ladder_type='women').count()
    ladder_total_teams = ladder_men_teams + ladder_women_teams

    active_challenges = LadderChallenge.query.filter(
        LadderChallenge.status.in_(['pending_acceptance', 'accepted'])
    ).count()

    first_day_of_month = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    ladder_matches_this_month = LadderMatch.query.filter(
        LadderMatch.verified == True,
        LadderMatch.completed_at >= first_day_of_month
    ).count()

    all_ladder_teams = LadderTeam.query.all()
    ladder_teams_with_matches = [t for t in all_ladder_teams if t.matches_played > 0]
    ladder_top_performers = []
    if ladder_teams_with_matches:
        sorted_by_win_rate = sorted(
            ladder_teams_with_matches, 
            key=lambda t: (t.wins / t.matches_played if t.matches_played > 0 else 0, t.wins), 
            reverse=True
        )
        ladder_top_performers = sorted_by_win_rate[:5]

    return render_template(
        "stats.html",
        teams=teams,
        team_streaks=team_streaks,
        teams_by_points=teams_by_points,
        teams_by_sets_diff=teams_by_sets_diff,
        teams_by_games_diff=teams_by_games_diff,
        teams_by_wins=teams_by_wins,
        teams_by_streak=teams_by_streak,
        ladder_total_teams=ladder_total_teams,
        ladder_men_teams=ladder_men_teams,
        ladder_women_teams=ladder_women_teams,
        active_challenges=active_challenges,
        ladder_matches_this_month=ladder_matches_this_month,
        ladder_top_performers=ladder_top_performers,
    )

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    """Admin login page"""
    if request.method == "POST":
        password = request.form.get("password", "").strip()
        admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")  # Default password if not set

        if password == admin_password:
            session['admin_authenticated'] = True
            session.permanent = True  # Keep session across browser restarts
            flash("Successfully logged in!", "success")
            return redirect(url_for('admin_panel'))
        else:
            flash("Incorrect password. Please try again.", "error")
            return redirect(url_for('admin_login'))

    # If already authenticated, redirect to admin panel
    if check_admin_auth():
        return redirect(url_for('admin_panel'))

    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    """Admin logout"""
    session.pop('admin_authenticated', None)
    flash("You have been logged out.", "success")
    return redirect(url_for('index'))


@app.route("/admin")
@require_admin_auth
def admin_panel():
    teams = Team.query.all()
    free_agents = FreeAgent.query.filter_by(paired=False).all()
    # Filter out draft matches from main query - only show live matches
    matches = Match.query.filter(
        db.or_(Match.is_draft == False, Match.is_draft == None)
    ).all()
    reschedules = Reschedule.query.filter_by(status="pending").all()
    substitutes = Substitute.query.filter_by(status="pending").all()
    # History (approved/denied)
    reschedules_history = Reschedule.query.filter(Reschedule.status != "pending").all()
    substitutes_history = Substitute.query.filter(Substitute.status != "pending").all()

    # Check for pending draft rounds
    pending_draft = Match.query.filter_by(is_draft=True).first()
    pending_draft_round = pending_draft.round if pending_draft else None

    # Get reschedule data for dashboard
    pending_reschedules_count = len(reschedules)
    max_reschedules = get_max_reschedules_per_round()

    # Calculate current and next round numbers (only from live matches)
    current_round = 0
    if matches:
        # Get the highest round number from existing live matches
        current_round = max([m.round for m in matches if m.round])
    next_round = current_round + 1

    # Check for free agent duplicates (already in teams)
    free_agent_status = []
    for fa in free_agents:
        # Check if this free agent's phone or email exists in Team table
        existing_team = Team.query.filter(
            db.or_(
                Team.player1_phone == fa.phone,
                Team.player2_phone == fa.phone,
                Team.player1_email == fa.email,
                Team.player2_email == fa.email
            )
        ).first()

        free_agent_status.append({
            'free_agent': fa,
            'in_team': existing_team,
            'status': 'duplicate' if existing_team else 'available'
        })

    # Check Swiss completion and playoff status
    swiss_complete, completed_rounds, total_swiss = check_swiss_completion()
    settings = LeagueSettings.query.first()

    # Determine if we should show playoff preview button
    show_playoff_preview = (
        swiss_complete and
        settings and
        settings.current_phase == "swiss" and
        not settings.playoffs_approved
    )

    # Ladder-specific data
    men_teams_count = LadderTeam.query.filter_by(gender='men').count()
    women_teams_count = LadderTeam.query.filter_by(gender='women').count()
    mixed_teams_count = LadderTeam.query.filter_by(gender='mixed').count()

    # Calculate division-specific counts
    men_active_challenges = LadderChallenge.query.join(
        LadderTeam, LadderChallenge.challenger_team_id == LadderTeam.id
    ).filter(
        LadderTeam.ladder_type == 'men',
        LadderChallenge.status.in_(['pending_acceptance', 'accepted'])
    ).count()
    
    women_active_challenges = LadderChallenge.query.join(
        LadderTeam, LadderChallenge.challenger_team_id == LadderTeam.id
    ).filter(
        LadderTeam.ladder_type == 'women',
        LadderChallenge.status.in_(['pending_acceptance', 'accepted'])
    ).count()
    
    mixed_active_challenges = LadderChallenge.query.join(
        LadderTeam, LadderChallenge.challenger_team_id == LadderTeam.id
    ).filter(
        LadderTeam.ladder_type == 'mixed',
        LadderChallenge.status.in_(['pending_acceptance', 'accepted'])
    ).count()

    men_pending_matches = LadderMatch.query.join(
        LadderTeam, LadderMatch.team_a_id == LadderTeam.id
    ).filter(
        LadderTeam.ladder_type == 'men',
        LadderMatch.status.in_(['pending', 'pending_scores', 'pending_opponent_score'])
    ).count()
    
    women_pending_matches = LadderMatch.query.join(
        LadderTeam, LadderMatch.team_a_id == LadderTeam.id
    ).filter(
        LadderTeam.ladder_type == 'women',
        LadderMatch.status.in_(['pending', 'pending_scores', 'pending_opponent_score'])
    ).count()
    
    mixed_pending_matches = LadderMatch.query.join(
        LadderTeam, LadderMatch.team_a_id == LadderTeam.id
    ).filter(
        LadderTeam.ladder_type == 'mixed',
        LadderMatch.status.in_(['pending', 'pending_scores', 'pending_opponent_score'])
    ).count()

    no_show_reports_count = LadderMatch.query.filter_by(status='no_show_reported').count()
    disputed_matches_count = LadderMatch.query.filter_by(disputed=True).count()

    men_on_holiday_count = LadderTeam.query.filter_by(
        ladder_type='men',
        holiday_mode_active=True
    ).count()

    women_on_holiday_count = LadderTeam.query.filter_by(
        ladder_type='women',
        holiday_mode_active=True
    ).count()

    mixed_on_holiday_count = LadderTeam.query.filter_by(
        ladder_type='mixed',
        holiday_mode_active=True
    ).count()

    # Pending payments
    pending_payments_men = LadderTeam.query.filter_by(
        gender='men',
        payment_received=False
    ).order_by(LadderTeam.created_at.desc()).all()

    pending_payments_women = LadderTeam.query.filter_by(
        gender='women',
        payment_received=False
    ).order_by(LadderTeam.created_at.desc()).all()

    pending_payments_mixed = LadderTeam.query.filter_by(
        gender='mixed',
        payment_received=False
    ).order_by(LadderTeam.created_at.desc()).all()

    # Get today's date and matches for Today's Matches section
    from datetime import datetime, date
    today_date = date.today()

    # Filter today's matches - only show matches that have been booked (confirmed or pending)
    todays_matches = []
    for match in matches:
        is_today = False
        
        # Check admin-set booking date first
        if match.booking_date_admin:
            try:
                from datetime import datetime as dt
                date_part = match.booking_date_admin.split(" at ")[0]
                admin_date = dt.strptime(date_part, "%Y-%m-%d").date()
                if admin_date == today_date:
                    is_today = True
            except:
                pass
        
        # Check regular match_datetime if not already matched as today
        if not is_today and match.match_datetime and match.match_datetime.date() == today_date:
            is_today = True
        
        # Add match if it's today and has booking details
        if is_today:
            if match.booking_details or match.booking_date_admin:
                todays_matches.append(match)
    
    # Sort today's matches by booking time (handle both admin dates and regular datetimes)
    def sort_todays_matches(m):
        if m.booking_date_admin:
            try:
                from datetime import datetime as dt
                date_part = m.booking_date_admin.split(" at ")[0]
                time_part = m.booking_date_admin.split(" at ")[1] if " at " in m.booking_date_admin else "00:00"
                return dt.strptime(f"{date_part} {time_part}", "%Y-%m-%d %H:%M")
            except:
                return datetime.max
        elif m.match_datetime:
            return m.match_datetime
        else:
            return datetime.max
    
    todays_matches.sort(key=sort_todays_matches)

    # Build Round Summary - grouped by round number, sorted by booking date within each round
    rounds_dict = {}
    for match in matches:
        round_num = match.round if match.round else 0
        if round_num not in rounds_dict:
            rounds_dict[round_num] = []
        
        team_a = Team.query.get(match.team_a_id)
        team_b = Team.query.get(match.team_b_id) if match.team_b_id else None
        
        booking_date = "Yet to be scheduled"
        booking_confirmed_status = "awaiting"
        
        # Check admin-set booking date first, then fall back to match_datetime
        if match.booking_date_admin:
            # Parse admin booking date and format consistently: "Wed, Dec 02"
            try:
                from datetime import datetime
                date_part = match.booking_date_admin.split(" at ")[0]  # Extract "2025-12-16" part
                admin_date = datetime.strptime(date_part, "%Y-%m-%d")
                booking_date = admin_date.strftime("%a, %b %d")
            except:
                booking_date = match.booking_date_admin
            booking_confirmed_status = "confirmed"
        elif match.match_datetime:
            booking_date = match.match_datetime.strftime("%a, %b %d")
            booking_confirmed_status = "confirmed" if match.booking_confirmed else "awaiting"
        
        score = ""
        score_confirmed_status = "awaiting"
        is_walkover = False
        
        # Check if it's a walkover
        if match.status == "walkover":
            is_walkover = True
            winner_team = Team.query.get(match.winner_id) if match.winner_id else None
            score = f"W - {winner_team.team_name if winner_team else 'Unknown'}"
            score_confirmed_status = "confirmed"
        # Check if score has been submitted (by either team or finalized)
        elif match.score_a and match.score_b:
            # Score is finalized - both teams have scores recorded
            score = f"{match.score_a}"
            # If both scores exist, it's confirmed (either via normal flow or admin entry)
            score_confirmed_status = "confirmed"
        elif match.score_submission_a or match.score_submission_b:
            # At least one team has submitted a score
            submitted_score = match.score_submission_a if match.score_submission_a else match.score_submission_b
            score = f"{submitted_score}"
            score_confirmed_status = "awaiting"
        elif match.status == "completed":
            # Match is completed but no score details
            score = "Completed"
            score_confirmed_status = "confirmed"
        
        # Determine which team needs to confirm booking
        booking_pending_team = None
        if booking_confirmed_status == "awaiting" and team_a and team_b:
            booking_pending_team = team_a.team_name
        
        # Determine which team needs to submit score
        score_pending_team = None
        if score_confirmed_status == "awaiting" and not is_walkover:
            if match.score_submission_a and not match.score_submission_b:
                score_pending_team = team_b.team_name if team_b else "Unknown"
            elif match.score_submission_b and not match.score_submission_a:
                score_pending_team = team_a.team_name if team_a else "Unknown"
            elif not match.score_submission_a and not match.score_submission_b and (match.score_submission_a is None or match.score_submission_b is None):
                score_pending_team = f"{team_a.team_name if team_a else 'Unknown'}/{team_b.team_name if team_b else 'Unknown'}"
        
        rounds_dict[round_num].append({
            'match': match,
            'team_a': team_a,
            'team_b': team_b,
            'booking_date': booking_date,
            'booking_confirmed_status': booking_confirmed_status,
            'booking_pending_team': booking_pending_team,
            'score': score,
            'score_confirmed_status': score_confirmed_status,
            'score_pending_team': score_pending_team,
            'is_walkover': is_walkover
        })
    
    # Sort matches within each round by booking date
    def get_sort_key(item):
        from datetime import datetime
        
        # Check admin booking date first
        if item['match'].booking_date_admin:
            try:
                date_part = item['match'].booking_date_admin.split(" at ")[0]
                date_obj = datetime.strptime(date_part, "%Y-%m-%d")
                return (0, date_obj)
            except:
                pass
        
        # Fall back to match_datetime
        if item['match'].match_datetime:
            return (0, item['match'].match_datetime)
        
        # Unscheduled matches go at the end
        return (1, '')
    
    for round_num in rounds_dict:
        rounds_dict[round_num].sort(key=get_sort_key)
    
    # Create sorted list of rounds (newest first)
    round_summary = []
    for round_num in sorted(rounds_dict.keys(), reverse=True):
        matches_in_round = rounds_dict[round_num]
        completed_count = len([m for m in matches_in_round if m['match'].status in ('completed', 'walkover')])
        
        # Get round deadline from first match in round (all matches share same deadline)
        round_deadline = None
        if matches_in_round:
            first_match = matches_in_round[0]['match']
            round_deadline = first_match.round_deadline
        
        round_summary.append({
            'round_number': round_num,
            'matches': matches_in_round,
            'total_matches': len(matches_in_round),
            'completed_matches': completed_count,
            'deadline': round_deadline
        })

    # Free Agents tab data with matching contact info check
    ladder_free_agents = LadderFreeAgent.query.order_by(LadderFreeAgent.created_at.desc()).all()
    
    # Check which free agents have matching email/phone with existing ladder teams (Men's and Women's only, exclude Mixed)
    ladder_free_agents_with_matches = []
    for agent in ladder_free_agents:
        # Check if this free agent's phone or email exists in LadderTeam table (only Men's and Women's, not Mixed)
        matching_teams = LadderTeam.query.filter(
            LadderTeam.ladder_type.in_(['men', 'women']),
            db.or_(
                LadderTeam.player1_phone == agent.phone,
                LadderTeam.player2_phone == agent.phone,
                LadderTeam.player1_email == agent.email,
                LadderTeam.player2_email == agent.email
            )
        ).all()
        
        ladder_free_agents_with_matches.append({
            'agent': agent,
            'has_match': len(matching_teams) > 0,
            'matching_teams': matching_teams
        })

    # Get all walkover matches for admin override tracking
    walkovers = Match.query.filter_by(status='walkover').order_by(Match.round.desc()).all()
    walkover_data = []
    for walkover in walkovers:
        team_a = Team.query.get(walkover.team_a_id)
        team_b = Team.query.get(walkover.team_b_id) if walkover.team_b_id else None
        winner = Team.query.get(walkover.winner_id) if walkover.winner_id else None
        walkover_data.append({
            'match': walkover,
            'team_a': team_a,
            'team_b': team_b,
            'winner': winner
        })

    # Default deadline for new round (1 week from now)
    from datetime import datetime, timedelta
    default_deadline = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

    # Knockout bracket status for admin panel
    knockout_status = {
        'has_knockout': False,
        'qf_matches': [],
        'sf_matches': [],
        'final_match': None,
        'qf_complete': False,
        'sf_complete': False,
        'final_complete': False,
        'can_generate_sf': False,
        'can_generate_final': False,
        'champion': None
    }
    
    # Get knockout matches
    qf_matches = Match.query.filter_by(phase='quarterfinal').all()
    sf_matches = Match.query.filter_by(phase='semifinal').all()
    final_match = Match.query.filter_by(phase='final').first()
    
    if qf_matches:
        knockout_status['has_knockout'] = True
        knockout_status['qf_matches'] = qf_matches
        knockout_status['qf_complete'] = all(m.winner_id for m in qf_matches)
        knockout_status['can_generate_sf'] = knockout_status['qf_complete'] and len(sf_matches) == 0
    
    if sf_matches:
        knockout_status['sf_matches'] = sf_matches
        knockout_status['sf_complete'] = all(m.winner_id for m in sf_matches)
        knockout_status['can_generate_final'] = knockout_status['sf_complete'] and final_match is None
    
    if final_match:
        knockout_status['final_match'] = final_match
        knockout_status['final_complete'] = final_match.winner_id is not None
        if knockout_status['final_complete']:
            knockout_status['champion'] = db.session.get(Team, final_match.winner_id)

    # Americano tournaments data (similar to admin_americano_tournaments route)
    tournaments = AmericanoTournament.query.order_by(AmericanoTournament.tournament_date.desc()).all()
    tournament_data = []
    for tournament in tournaments:
        participating_ids = []
        if tournament.participating_free_agents:
            import json
            try:
                participating_ids = json.loads(tournament.participating_free_agents)
            except:
                pass

        participants_count = len(participating_ids)

        matches_americano = AmericanoMatch.query.filter_by(tournament_id=tournament.id).all()
        matches_count = len(matches_americano)
        completed_matches = len([m for m in matches_americano if m.status == 'completed'])

        tournament_data.append({
            'tournament': tournament,
            'participants_count': participants_count,
            'matches_count': matches_count,
            'completed_matches': completed_matches
        })

    return render_template(
        "admin.html",
        teams=teams,
        free_agents=free_agents,
        free_agent_status=free_agent_status,
        matches=matches,
        todays_matches=todays_matches,
        round_summary=round_summary,
        reschedules=reschedules,
        substitutes=substitutes,
        reschedules_history=reschedules_history,
        substitutes_history=substitutes_history,
        pending_reschedules_count=pending_reschedules_count,
        max_reschedules=max_reschedules,
        swiss_complete=swiss_complete,
        completed_rounds=completed_rounds,
        total_swiss=total_swiss,
        show_playoff_preview=show_playoff_preview,
        settings=settings,
        walkover_data=walkover_data,
        current_round=current_round,
        next_round=next_round,
        men_teams_count=men_teams_count,
        women_teams_count=women_teams_count,
        mixed_teams_count=mixed_teams_count,
        men_active_challenges=men_active_challenges,
        women_active_challenges=women_active_challenges,
        mixed_active_challenges=mixed_active_challenges,
        men_pending_matches=men_pending_matches,
        women_pending_matches=women_pending_matches,
        mixed_pending_matches=mixed_pending_matches,
        no_show_reports_count=no_show_reports_count,
        disputed_matches_count=disputed_matches_count,
        men_on_holiday_count=men_on_holiday_count,
        women_on_holiday_count=women_on_holiday_count,
        mixed_on_holiday_count=mixed_on_holiday_count,
        pending_payments_men=pending_payments_men,
        pending_payments_women=pending_payments_women,
        pending_payments_mixed=pending_payments_mixed,
        today_date=today_date,
        ladder_free_agents=ladder_free_agents,
        ladder_free_agents_with_matches=ladder_free_agents_with_matches,
        tournament_data=tournament_data,
        pending_draft_round=pending_draft_round,
        default_deadline=default_deadline,
        knockout_status=knockout_status,
    )


@app.route("/admin/ladder/toggle-payment", methods=["POST"])
@require_admin_auth
def admin_ladder_toggle_payment():
    """Toggle payment status for a ladder team"""
    team_id = request.form.get("team_id", type=int)

    if not team_id:
        flash("Team ID is required", "error")
        return redirect(url_for('admin_panel'))

    team = LadderTeam.query.get(team_id)
    if not team:
        flash("Team not found", "error")
        return redirect(url_for('admin_panel'))

    # Toggle payment status
    team.payment_received = not team.payment_received
    db.session.commit()

    if team.payment_received:
        flash(f"✓ Payment confirmed for {team.team_name}. Team is now visible in rankings.", "success")
    else:
        flash(f"Payment status removed for {team.team_name}. Team hidden from rankings.", "success")

    return redirect(url_for('admin_ladder_rankings', ladder_type=team.ladder_type))


@app.route("/admin/ladder/rankings/<ladder_type>")
@require_admin_auth
def admin_ladder_rankings(ladder_type):
    if ladder_type not in ['men', 'women', 'mixed']:
        flash("Invalid ladder type", "error")
        return redirect(url_for('admin_panel'))

    teams = LadderTeam.query.filter_by(gender=ladder_type).order_by(LadderTeam.current_rank).all()

    total_teams = len(teams)
    if ladder_type == 'men':
        division_title = "Men's Division"
    elif ladder_type == 'women':
        division_title = "Women's Division"
    else:
        division_title = "Mixed Division"

    teams_with_status = []
    for idx, team in enumerate(teams, start=1):
        status = 'available'
        status_color = 'green'
        status_text = 'Available'

        if team.holiday_mode_active:
            status = 'holiday'
            status_color = 'blue'
            status_text = 'Holiday'

        teams_with_status.append({
            'team': team,
            'status': status,
            'status_color': status_color,
            'status_text': status_text,
            'sets_diff': team.sets_for - team.sets_against,
            'games_diff': team.games_for - team.games_against,
            'display_rank': idx,
        })

    return render_template(
        "admin_ladder_rankings.html",
        teams=teams_with_status,
        total_teams=total_teams,
        ladder_type=ladder_type,
        division_title=division_title
    )


@app.route("/admin/ladder/challenges/<ladder_type>")
@require_admin_auth
def admin_ladder_challenges(ladder_type):
    """Admin page to manage all ladder challenges for a division"""
    from datetime import datetime

    if ladder_type not in ['men', 'women', 'mixed']:
        flash("Invalid ladder type", "error")
        return redirect(url_for('admin_panel'))

    if ladder_type == 'men':
        division_title = "Men's Division"
    elif ladder_type == 'women':
        division_title = "Women's Division"
    else:
        division_title = "Mixed Division"

    all_challenges = LadderChallenge.query.filter_by(ladder_type=ladder_type).order_by(
        LadderChallenge.created_at.desc()
    ).all()

    now = datetime.now()

    pending_acceptance = []
    accepted = []
    expired = []
    rejected = []

    for challenge in all_challenges:
        challenger = LadderTeam.query.get(challenge.challenger_team_id)
        challenged = LadderTeam.query.get(challenge.challenged_team_id)

        challenge_data = {
            'challenge': challenge,
            'challenger': challenger,
            'challenged': challenged,
            'is_overdue': challenge.acceptance_deadline and now > challenge.acceptance_deadline
        }

        # Skip challenges that are completed (match was verified)
        if challenge.status == 'completed':
            continue

        if challenge.status == 'pending_acceptance':
            pending_acceptance.append(challenge_data)
        elif challenge.status == 'accepted':
            accepted.append(challenge_data)
        elif challenge.status == 'expired':
            expired.append(challenge_data)
        elif challenge.status == 'rejected':
            rejected.append(challenge_data)

    return render_template(
        "admin_ladder_challenges.html",
        ladder_type=ladder_type,
        division_title=division_title,
        pending_acceptance=pending_acceptance,
        accepted=accepted,
        expired=expired,
        rejected=rejected
    )


@app.route("/admin/ladder/challenge/force-accept/<int:challenge_id>", methods=["POST"])
@require_admin_auth
def admin_force_accept_challenge(challenge_id):
    """Admin force accepts a pending challenge"""
    from utils import send_email_notification
    
    challenge = LadderChallenge.query.get(challenge_id)
    if not challenge:
        flash("Challenge not found", "error")
        return redirect(request.referrer or url_for('admin_panel'))
    
    if challenge.status != 'pending_acceptance':
        flash("Challenge is not pending acceptance", "error")
        return redirect(request.referrer or url_for('admin_panel'))
    
    challenger_team = LadderTeam.query.get(challenge.challenger_team_id)
    challenged_team = LadderTeam.query.get(challenge.challenged_team_id)
    
    # Accept the challenge
    challenge.status = 'accepted'
    challenger_team.is_locked = True
    challenged_team.is_locked = True
    db.session.commit()
    
    # Create match if not exists
    existing_match = LadderMatch.query.filter_by(challenge_id=challenge.id).first()
    if not existing_match:
        match = LadderMatch(
            challenge_id=challenge.id,
            team_a_id=challenger_team.id,
            team_b_id=challenged_team.id,
            ladder_type=challenge.ladder_type,
            status='pending'
        )
        db.session.add(match)
        db.session.commit()
    
    # Send notifications
    challenger_message = f"""Challenge Accepted (Admin Force)

Your challenge against {challenged_team.team_name} has been accepted by admin.

Challenge Details:
- Opponent: {challenged_team.team_name} ({challenged_team.player1_name} & {challenged_team.player2_name})
- Their Rank: #{challenged_team.current_rank}
- Complete by: {challenge.completion_deadline.strftime('%b %d, %Y') if challenge.completion_deadline else 'N/A'}

Both teams are now locked and must complete the match by the deadline.

Regards,
BD Padel Ladder Team
"""
    
    challenged_message = f"""Challenge Accepted (Admin Force)

{challenger_team.team_name} has been accepted to challenge you (admin force).

Challenge Details:
- Challenger: {challenger_team.team_name} ({challenger_team.player1_name} & {challenger_team.player2_name})
- Their Rank: #{challenger_team.current_rank}
- Complete by: {challenge.completion_deadline.strftime('%b %d, %Y') if challenge.completion_deadline else 'N/A'}

Both teams are now locked and must complete the match by the deadline.

Regards,
BD Padel Ladder Team
"""
    
    if challenger_team.contact_preference_email:
        if challenger_team.player1_email:
            send_email_notification(challenger_team.player1_email, "Challenge Accepted", challenger_message)
        if challenger_team.player2_email and challenger_team.player2_email != challenger_team.player1_email:
            send_email_notification(challenger_team.player2_email, "Challenge Accepted", challenger_message)
    
    if challenged_team.contact_preference_email:
        if challenged_team.player1_email:
            send_email_notification(challenged_team.player1_email, "Challenge Received", challenged_message)
        if challenged_team.player2_email and challenged_team.player2_email != challenged_team.player1_email:
            send_email_notification(challenged_team.player2_email, "Challenge Received", challenged_message)
    
    flash("Challenge accepted successfully. Both teams are now locked.", "success")
    return redirect(request.referrer or url_for('admin_panel'))


@app.route("/admin/ladder/challenge/force-reject/<int:challenge_id>", methods=["POST"])
@require_admin_auth
def admin_force_reject_challenge(challenge_id):
    """Admin force rejects a pending challenge"""
    from utils import send_email_notification
    
    challenge = LadderChallenge.query.get(challenge_id)
    if not challenge:
        flash("Challenge not found", "error")
        return redirect(request.referrer or url_for('admin_panel'))
    
    if challenge.status != 'pending_acceptance':
        flash("Challenge is not pending acceptance", "error")
        return redirect(request.referrer or url_for('admin_panel'))
    
    challenger_team = LadderTeam.query.get(challenge.challenger_team_id)
    challenged_team = LadderTeam.query.get(challenge.challenged_team_id)
    
    # Reject the challenge
    challenge.status = 'rejected'
    challenged_team.is_locked = False
    db.session.commit()
    
    # Send notifications
    challenger_message = f"""Challenge Rejected (Admin Force)

Your challenge against {challenged_team.team_name} has been rejected by admin.

Challenge Details:
- Challenged Team: {challenged_team.team_name} ({challenged_team.player1_name} & {challenged_team.player2_name})
- Their Rank: #{challenged_team.current_rank}

You are now unlocked and can send new challenges.

Regards,
BD Padel Ladder Team
"""
    
    challenged_message = f"""Challenge Rejected (Admin Force)

Your challenge from {challenger_team.team_name} has been rejected by admin.

Challenge Details:
- Challenger: {challenger_team.team_name} ({challenger_team.player1_name} & {challenger_team.player2_name})
- Their Rank: #{challenger_team.current_rank}

You are now unlocked and available for new challenges.

Regards,
BD Padel Ladder Team
"""
    
    if challenger_team.contact_preference_email:
        if challenger_team.player1_email:
            send_email_notification(challenger_team.player1_email, "Challenge Rejected", challenger_message)
        if challenger_team.player2_email and challenger_team.player2_email != challenger_team.player1_email:
            send_email_notification(challenger_team.player2_email, "Challenge Rejected", challenger_message)
    
    if challenged_team.contact_preference_email:
        if challenged_team.player1_email:
            send_email_notification(challenged_team.player1_email, "Challenge Rejected", challenged_message)
        if challenged_team.player2_email and challenged_team.player2_email != challenged_team.player1_email:
            send_email_notification(challenged_team.player2_email, "Challenge Rejected", challenged_message)
    
    flash("Challenge rejected successfully. Teams are now unlocked.", "success")
    return redirect(request.referrer or url_for('admin_panel'))


@app.route("/admin/ladder/challenge/cancel/<int:challenge_id>", methods=["POST"])
@require_admin_auth
def admin_cancel_challenge(challenge_id):
    """Admin cancels a challenge (pending or accepted)"""
    from utils import send_email_notification
    
    challenge = LadderChallenge.query.get(challenge_id)
    if not challenge:
        flash("Challenge not found", "error")
        return redirect(request.referrer or url_for('admin_panel'))
    
    if challenge.status not in ['pending_acceptance', 'accepted']:
        flash("Can only cancel pending or accepted challenges", "error")
        return redirect(request.referrer or url_for('admin_panel'))
    
    challenger_team = LadderTeam.query.get(challenge.challenger_team_id)
    challenged_team = LadderTeam.query.get(challenge.challenged_team_id)
    
    # Cancel the challenge
    challenge.status = 'cancelled'
    challenger_team.is_locked = False
    challenged_team.is_locked = False
    db.session.commit()
    
    # Delete match if exists and no scores submitted
    match = LadderMatch.query.filter_by(challenge_id=challenge.id).first()
    if match and not match.team_a_submitted and not match.team_b_submitted:
        db.session.delete(match)
        db.session.commit()
    
    # Send notifications
    challenger_message = f"""Challenge Cancelled (Admin)

Your challenge against {challenged_team.team_name} has been cancelled by admin.

Challenge Details:
- Challenged Team: {challenged_team.team_name} ({challenged_team.player1_name} & {challenged_team.player2_name})
- Their Rank: #{challenged_team.current_rank}

Both teams are now unlocked.

Regards,
BD Padel Ladder Team
"""
    
    challenged_message = f"""Challenge Cancelled (Admin)

The challenge from {challenger_team.team_name} has been cancelled by admin.

Challenge Details:
- Challenger: {challenger_team.team_name} ({challenger_team.player1_name} & {challenger_team.player2_name})
- Their Rank: #{challenger_team.current_rank}

Both teams are now unlocked.

Regards,
BD Padel Ladder Team
"""
    
    if challenger_team.contact_preference_email:
        if challenger_team.player1_email:
            send_email_notification(challenger_team.player1_email, "Challenge Cancelled", challenger_message)
        if challenger_team.player2_email and challenger_team.player2_email != challenger_team.player1_email:
            send_email_notification(challenger_team.player2_email, "Challenge Cancelled", challenger_message)
    
    if challenged_team.contact_preference_email:
        if challenged_team.player1_email:
            send_email_notification(challenged_team.player1_email, "Challenge Cancelled", challenged_message)
        if challenged_team.player2_email and challenged_team.player2_email != challenged_team.player1_email:
            send_email_notification(challenged_team.player2_email, "Challenge Cancelled", challenged_message)
    
    flash("Challenge cancelled successfully. Teams are now unlocked.", "success")
    return redirect(request.referrer or url_for('admin_ladder_challenges', ladder_type=challenge.ladder_type))


@app.route("/admin/ladder/challenge/reactivate/<int:challenge_id>", methods=["POST"])
@require_admin_auth
def admin_reactivate_challenge(challenge_id):
    """Admin reactivates an expired challenge by extending its deadline."""
    from datetime import datetime, timedelta
    
    challenge = LadderChallenge.query.get_or_404(challenge_id)
    
    # Reset status and give a fresh 48-hour window
    challenge.status = 'pending_acceptance'
    challenge.acceptance_deadline = datetime.now() + timedelta(hours=48)
    
    db.session.commit()
    flash("Challenge reactivated successfully for 48 hours.", "success")
    return redirect(request.referrer or url_for('admin_ladder_challenges', ladder_type=challenge.ladder_type))


@app.route("/admin/ladder/matches/<ladder_type>")
@require_admin_auth
def admin_ladder_matches(ladder_type):
    """Admin page to manage all ladder matches for a division"""
    from datetime import datetime

    if ladder_type not in ['men', 'women', 'mixed']:
        flash("Invalid ladder type", "error")
        return redirect(url_for('admin_panel'))

    if ladder_type == 'men':
        division_title = "Men's Division"
    elif ladder_type == 'women':
        division_title = "Women's Division"
    else:
        division_title = "Mixed Division"

    all_matches = LadderMatch.query.filter_by(ladder_type=ladder_type).order_by(
        LadderMatch.created_at.desc()
    ).all()

    pending_scores = []
    disputed = []
    no_shows = []
    completed = []

    for match in all_matches:
        team_a = LadderTeam.query.get(match.team_a_id)
        team_b = LadderTeam.query.get(match.team_b_id)

        match_data = {
            'match': match,
            'team_a': team_a,
            'team_b': team_b,
        }

        if match.disputed:
            disputed.append(match_data)
        elif match.reported_no_show_team_id and not match.no_show_verified:
            no_shows.append(match_data)
        elif match.verified or match.status == 'completed':
            if len(completed) < 20:
                completed.append(match_data)
        elif match.status == 'pending':
            pending_scores.append(match_data)

    return render_template(
        "admin_ladder_matches.html",
        ladder_type=ladder_type,
        division_title=division_title,
        pending_scores=pending_scores,
        disputed=disputed,
        no_shows=no_shows,
        completed=completed
    )


@app.route("/admin/ladder/dispute/resolve/<int:match_id>", methods=["GET", "POST"])
@require_admin_auth
def admin_ladder_dispute_resolve(match_id):
    """Admin page to resolve disputed ladder match scores"""
    from datetime import datetime
    from utils import swap_ladder_ranks, update_ladder_team_stats, send_email_notification

    match = LadderMatch.query.get_or_404(match_id)
    team_a = LadderTeam.query.get(match.team_a_id)
    team_b = LadderTeam.query.get(match.team_b_id)

    if request.method == "POST":
        try:
            set1_a = request.form.get("set1_a", type=int)
            set1_b = request.form.get("set1_b", type=int)
            set2_a = request.form.get("set2_a", type=int)
            set2_b = request.form.get("set2_b", type=int)
            set3_a = request.form.get("set3_a", type=int, default=0)
            set3_b = request.form.get("set3_b", type=int, default=0)
            winner_choice = request.form.get("winner")
            admin_notes = request.form.get("admin_notes", "")

            if not all([set1_a is not None, set1_b is not None, set2_a is not None, set2_b is not None, winner_choice]):
                flash("Please fill in all required fields", "error")
                return redirect(url_for('admin_ladder_dispute_resolve', match_id=match_id))

            sets_a = 0
            sets_b = 0
            games_a = set1_a + set2_a + (set3_a or 0)
            games_b = set1_b + set2_b + (set3_b or 0)

            if set1_a > set1_b:
                sets_a += 1
            else:
                sets_b += 1

            if set2_a > set2_b:
                sets_a += 1
            else:
                sets_b += 1

            if set3_a and set3_b:
                if set3_a > set3_b:
                    sets_a += 1
                else:
                    sets_b += 1

            match.team_a_score_set1 = set1_a
            match.team_a_score_set2 = set2_a
            match.team_a_score_set3 = set3_a
            match.team_b_score_set1 = set1_b
            match.team_b_score_set2 = set2_b
            match.team_b_score_set3 = set3_b

            match.sets_a = sets_a
            match.sets_b = sets_b
            match.games_a = games_a
            match.games_b = games_b

            if winner_choice == "team_a":
                match.winner_id = team_a.id
                winner_team = team_a
                loser_team = team_b
            elif winner_choice == "team_b":
                match.winner_id = team_b.id
                winner_team = team_b
                loser_team = team_a
            else:
                match.winner_id = None
                winner_team = None
                loser_team = None

            match.status = 'completed'
            match.disputed = False
            match.verified = True
            match.completed_at = datetime.now()

            if winner_team and loser_team:
                update_ladder_team_stats(match, winner_team, loser_team)
                rank_changes = swap_ladder_ranks(winner_team, loser_team, match.ladder_type)

                match.winner_old_rank = rank_changes['winner']['old']
                match.winner_new_rank = rank_changes['winner']['new']
                match.loser_old_rank = rank_changes['loser']['old']
                match.loser_new_rank = rank_changes['loser']['new']

            db.session.commit()

            email_body_a = f"""Hi {team_a.player1_name},

MATCH DISPUTE RESOLVED

Your disputed match has been reviewed and resolved by admin.

Match Details:
- Opponent: {team_b.team_name}
- Final Score: {set1_a}-{set1_b}, {set2_a}-{set2_b}{',' + str(set3_a) + '-' + str(set3_b) if set3_a else ''}
- Winner: {winner_team.team_name if winner_team else 'Draw'}
- Admin Notes: {admin_notes}

Your new rank: #{team_a.current_rank}

- BD Padel League
"""

            email_body_b = f"""Hi {team_b.player1_name},

MATCH DISPUTE RESOLVED

Your disputed match has been reviewed and resolved by admin.

Match Details:
- Opponent: {team_a.team_name}
- Final Score: {set1_b}-{set1_a}, {set2_b}-{set2_a}{',' + str(set3_b) + '-' + str(set3_a) if set3_b else ''}
- Winner: {winner_team.team_name if winner_team else 'Draw'}
- Admin Notes: {admin_notes}

Your new rank: #{team_b.current_rank}

- BD Padel League
"""

            if team_a.player1_email:
                send_email_notification(team_a.player1_email, "Match Dispute Resolved", email_body_a)
            if team_a.player2_email:
                send_email_notification(team_a.player2_email, "Match Dispute Resolved", email_body_a)
            if team_b.player1_email:
                send_email_notification(team_b.player1_email, "Match Dispute Resolved", email_body_b)
            if team_b.player2_email:
                send_email_notification(team_b.player2_email, "Match Dispute Resolved", email_body_b)

            flash("Match dispute resolved successfully!", "success")
            return redirect(url_for('admin_ladder_matches', ladder_type=match.ladder_type))

        except Exception as e:
            db.session.rollback()
            flash(f"Error resolving dispute: {str(e)}", "error")
            return redirect(url_for('admin_ladder_dispute_resolve', match_id=match_id))

    return render_template(
        "admin_ladder_dispute_resolve.html",
        match=match,
        team_a=team_a,
        team_b=team_b
    )


@app.route("/admin/ladder/no-show/process/<int:match_id>", methods=["POST"])
@require_admin_auth
def admin_ladder_no_show_process(match_id):
    """Process admin decision on no-show report"""
    from datetime import datetime
    from utils import swap_ladder_ranks, apply_rank_penalty, update_ladder_team_stats, send_email_notification

    match = LadderMatch.query.get_or_404(match_id)
    team_a = LadderTeam.query.get(match.team_a_id)
    team_b = LadderTeam.query.get(match.team_b_id)

    action = request.form.get("action")
    admin_notes = request.form.get("admin_notes", "")

    if match.status == 'completed':
        flash("Cannot process no-show - match already completed", "error")
        return redirect(url_for('admin_ladder_matches', ladder_type=match.ladder_type))

    try:
        if action == "approve":
            no_show_team_id = match.reported_no_show_team_id
            reporting_team_id = match.reported_by_team_id

            if no_show_team_id == team_a.id:
                opponent_team_name = team_b.team_name
                no_show_team = team_a
                winner_team = team_b
            else:
                opponent_team_name = team_a.team_name
                no_show_team = team_b
                winner_team = team_a

            penalty_result = apply_rank_penalty(no_show_team, 1, f"No-show for match vs {winner_team.team_name}", match.ladder_type)

            match.winner_id = winner_team.id
            match.sets_a = 2 if winner_team.id == team_a.id else 0
            match.sets_b = 2 if winner_team.id == team_b.id else 0
            match.games_a = 12 if winner_team.id == team_a.id else 0
            match.games_b = 12 if winner_team.id == team_b.id else 0
            match.status = 'completed_no_show'
            match.no_show_verified = True
            match.verified = True
            match.completed_at = datetime.now()

            update_ladder_team_stats(match, winner_team, no_show_team)

            db.session.commit()

            email_winner = f"""Hi {winner_team.player1_name},

NO-SHOW APPROVED - YOU WIN

The admin has approved the no-show report for your match.

Match Details:
- Opponent: {no_show_team.team_name} (No-Show)
- Result: Win by No-Show
- Admin Notes: {admin_notes}

Your new rank: #{winner_team.current_rank}

- BD Padel League
"""

            email_no_show = f"""Hi {no_show_team.player1_name},

NO-SHOW PENALTY APPLIED

The admin has confirmed your no-show for the match vs {winner_team.team_name}.

Penalties:
- Match Result: Loss by No-Show
- Rank Penalty: -1 rank
- New Rank: #{no_show_team.current_rank}
- Admin Notes: {admin_notes}

Please ensure you attend all scheduled matches in the future.

- BD Padel League
"""

            if winner_team.player1_email:
                send_email_notification(winner_team.player1_email, "No-Show Approved - You Win", email_winner)
            if winner_team.player2_email:
                send_email_notification(winner_team.player2_email, "No-Show Approved - You Win", email_winner)
            if no_show_team.player1_email:
                send_email_notification(no_show_team.player1_email, "No-Show Penalty Applied", email_no_show)
            if no_show_team.player2_email:
                send_email_notification(no_show_team.player2_email, "No-Show Penalty Applied", email_no_show)

            flash("No-show approved and penalties applied", "success")

        elif action == "reject":
            match.status = 'pending'
            match.reported_no_show_team_id = None
            match.reported_by_team_id = None
            match.no_show_report_date = None
            match.no_show_notes = None

            db.session.commit()

            email_body = f"""Hi,

NO-SHOW REPORT REJECTED

The admin has rejected the no-show report for your match.

Match Details:
- Teams: {team_a.team_name} vs {team_b.team_name}
- Status: Match must be played
- Admin Notes: {admin_notes}

Please coordinate with your opponent to complete the match.

- BD Padel League
"""

            if team_a.player1_email:
                send_email_notification(team_a.player1_email, "No-Show Report Rejected", email_body)
            if team_a.player2_email:
                send_email_notification(team_a.player2_email, "No-Show Report Rejected", email_body)
            if team_b.player1_email:
                send_email_notification(team_b.player1_email, "No-Show Report Rejected", email_body)
            if team_b.player2_email:
                send_email_notification(team_b.player2_email, "No-Show Report Rejected", email_body)

            flash("No-show report rejected - match reset to pending", "success")

        return redirect(url_for('admin_ladder_matches', ladder_type=match.ladder_type))

    except Exception as e:
        db.session.rollback()
        flash(f"Error processing no-show: {str(e)}", "error")
        return redirect(url_for('admin_ladder_matches', ladder_type=match.ladder_type))


@app.route("/admin/ladder/team/edit/<int:team_id>", methods=["GET", "POST"])
@require_admin_auth
def admin_ladder_edit_team(team_id):
    """Edit ladder team details"""
    from datetime import datetime
    from utils import normalize_phone_number, normalize_team_name, send_email_notification

    team = LadderTeam.query.get_or_404(team_id)
    ladder_type = team.ladder_type

    if request.method == "POST":
        try:
            team_name = request.form.get("team_name", "").strip()
            player1_name = request.form.get("player1_name", "").strip()
            player1_email = request.form.get("player1_email", "").strip()
            player1_phone = request.form.get("player1_phone", "").strip()
            player2_name = request.form.get("player2_name", "").strip()
            player2_email = request.form.get("player2_email", "").strip()
            player2_phone = request.form.get("player2_phone", "").strip()
            # Handle contact preferences - default to email if neither is selected
            contact_preference_email = "contact_preference_email" in request.form
            contact_preference_whatsapp = "contact_preference_whatsapp" in request.form
            
            # If neither is selected, default to email
            if not contact_preference_email and not contact_preference_whatsapp:
                contact_preference_email = True

            if not all([team_name, player1_name, player1_phone, player2_name, player2_phone]):
                flash("All required fields must be filled", "error")
                return redirect(url_for('admin_ladder_edit_team', team_id=team_id))

            canonical_name = normalize_team_name(team_name)
            existing_team = LadderTeam.query.filter(
                LadderTeam.team_name_canonical == canonical_name,
                LadderTeam.id != team_id,
                LadderTeam.ladder_type == ladder_type
            ).first()

            if existing_team:
                flash(f"Team name '{team_name}' is already taken in this division", "error")
                return redirect(url_for('admin_ladder_edit_team', team_id=team_id))

            old_team_name = team.team_name

            team.team_name = team_name
            team.team_name_canonical = canonical_name
            team.player1_name = player1_name
            team.player1_email = player1_email or None
            team.player1_phone = normalize_phone_number(player1_phone)
            team.player2_name = player2_name
            team.player2_email = player2_email or None
            team.player2_phone = normalize_phone_number(player2_phone)
            team.contact_preference_email = contact_preference_email
            team.contact_preference_whatsapp = contact_preference_whatsapp
            team.updated_at = datetime.now()

            db.session.commit()

            email_body = f"""Hi {team.player1_name},

TEAM DETAILS UPDATED

Your ladder team details have been updated by an administrator.

Updated Team: {team.team_name}
Previous Name: {old_team_name}
Division: {ladder_type.capitalize()} Ladder
Current Rank: #{team.current_rank}

Player 1: {team.player1_name} ({team.player1_email or team.player1_phone})
Player 2: {team.player2_name} ({team.player2_email or team.player2_phone})

If you have any questions about these changes, please contact the admin.

- BD Padel League
"""

            if team.contact_preference_email:
                if team.player1_email:
                    send_email_notification(team.player1_email, "Team Details Updated", email_body)
                if team.player2_email and team.player2_email != team.player1_email:
                    send_email_notification(team.player2_email, "Team Details Updated", email_body)

            flash(f"Team '{team.team_name}' updated successfully!", "success")
            return redirect(url_for('admin_ladder_rankings', ladder_type=ladder_type))

        except Exception as e:
            db.session.rollback()
            flash(f"Error updating team: {str(e)}", "error")
            return redirect(url_for('admin_ladder_edit_team', team_id=team_id))

    return render_template("admin_edit_team.html", team=team, is_ladder=True)


@app.route("/admin/ladder/team/delete/<int:team_id>", methods=["POST"])
@require_admin_auth
def admin_ladder_delete_team(team_id):
    """Delete ladder team and adjust rankings"""
    from utils import send_email_notification

    team = LadderTeam.query.get_or_404(team_id)
    ladder_type = team.ladder_type
    team_rank = team.current_rank
    team_name = team.team_name

    active_challenges = LadderChallenge.query.filter(
        db.or_(
            LadderChallenge.challenger_team_id == team_id,
            LadderChallenge.challenged_team_id == team_id
        ),
        LadderChallenge.status.in_(['pending_acceptance', 'accepted'])
    ).count()

    if active_challenges > 0:
        flash(f"Cannot delete team - they have {active_challenges} active challenge(s). Please resolve or cancel these first.", "error")
        return redirect(url_for('admin_ladder_rankings', ladder_type=ladder_type))

    pending_matches = LadderMatch.query.filter(
        db.or_(
            LadderMatch.team_a_id == team_id,
            LadderMatch.team_b_id == team_id
        ),
        LadderMatch.status == 'pending'
    ).count()

    if pending_matches > 0:
        flash(f"Cannot delete team - they have {pending_matches} pending match(es). Please resolve these first.", "error")
        return redirect(url_for('admin_ladder_rankings', ladder_type=ladder_type))

    try:
        teams_to_move_up = LadderTeam.query.filter(
            LadderTeam.gender == ladder_type,
            LadderTeam.current_rank > team_rank
        ).all()

        for t in teams_to_move_up:
            t.current_rank -= 1

        player1_email = team.player1_email
        player2_email = team.player2_email
        contact_email = team.contact_preference_email

        db.session.delete(team)
        db.session.commit()

        email_body = f"""Hi {team.player1_name},

TEAM REMOVED FROM LADDER

Your team "{team_name}" has been removed from the {ladder_type.capitalize()} Ladder by an administrator.

Previous Rank: #{team_rank}
Reason: Administrative decision

If you believe this was done in error or have questions, please contact the admin immediately.

- BD Padel League
"""

        if contact_email:
            if player1_email:
                send_email_notification(player1_email, "Team Removed from Ladder", email_body)
            if player2_email and player2_email != player1_email:
                send_email_notification(player2_email, "Team Removed from Ladder", email_body)

        flash(f"Team '{team_name}' deleted successfully. {len(teams_to_move_up)} team(s) moved up in rankings.", "success")
        return redirect(url_for('admin_ladder_rankings', ladder_type=ladder_type))

    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting team: {str(e)}", "error")
        return redirect(url_for('admin_ladder_rankings', ladder_type=ladder_type))


@app.route("/admin/ladder/team/adjust-rank", methods=["POST"])
@require_admin_auth
def admin_ladder_adjust_rank():
    """Manually adjust a team's rank on the ladder"""
    from utils import adjust_ladder_ranks, send_email_notification

    team_id = request.form.get("team_id", type=int)
    new_rank = request.form.get("new_rank", type=int)

    if not team_id or not new_rank:
        flash("Team ID and new rank are required", "error")
        return redirect(url_for('admin_panel'))

    team = LadderTeam.query.get_or_404(team_id)
    ladder_type = team.gender

    try:
        result = adjust_ladder_ranks(team, new_rank, ladder_type)

        if not result.get('success'):
            flash(result.get('message', 'Failed to adjust rank'), "error")
            return redirect(url_for('admin_ladder_rankings', ladder_type=ladder_type))

        old_rank = result['old_rank']
        new_rank = result['new_rank']
        affected_teams = result['affected_teams']

        email_body = f"""Hi {team.player1_name},

RANK ADJUSTED BY ADMIN

Your team's rank has been manually adjusted by an administrator.

Team: {team.team_name}
Old Rank: #{old_rank}
New Rank: #{new_rank}
Change: {"+" if new_rank > old_rank else ""}{new_rank - old_rank} positions

If you have questions about this adjustment, please contact the admin.

- BD Padel League
"""

        if team.contact_preference_email:
            if team.player1_email:
                send_email_notification(team.player1_email, f"Rank Adjusted: #{old_rank} → #{new_rank}", email_body)
            if team.player2_email and team.player2_email != team.player1_email:
                send_email_notification(team.player2_email, f"Rank Adjusted: #{old_rank} → #{new_rank}", email_body)

        for affected in affected_teams:
            affected_team = LadderTeam.query.get(affected['team_id'])
            if affected_team and affected_team.contact_preference_email:
                affected_email = f"""Hi {affected_team.player1_name},

RANK ADJUSTMENT NOTIFICATION

Due to an admin rank adjustment, your team's rank has been updated.

Team: {affected_team.team_name}
Old Rank: #{affected['old_rank']}
New Rank: #{affected['new_rank']}

This change was made to accommodate the adjustment of another team.

- BD Padel League
"""
                if affected_team.player1_email:
                    send_email_notification(affected_team.player1_email, "Rank Update", affected_email)
                if affected_team.player2_email and affected_team.player2_email != affected_team.player1_email:
                    send_email_notification(affected_team.player2_email, "Rank Update", affected_email)

        flash(f"Rank adjusted successfully! {team.team_name}: #{old_rank} → #{new_rank}. {len(affected_teams)} other team(s) affected.", "success")
        return redirect(url_for('admin_ladder_rankings', ladder_type=ladder_type))

    except Exception as e:
        db.session.rollback()
        flash(f"Error adjusting rank: {str(e)}", "error")
        return redirect(url_for('admin_ladder_rankings', ladder_type=ladder_type))


@app.route("/admin/ladder/team/toggle-holiday", methods=["POST"])
@require_admin_auth
def admin_ladder_toggle_holiday():
    """Toggle holiday mode for a ladder team"""
    from datetime import datetime
    from utils import send_email_notification

    team_id = request.form.get("team_id", type=int)

    if not team_id:
        flash("Team ID is required", "error")
        return redirect(url_for('admin_panel'))

    team = LadderTeam.query.get_or_404(team_id)
    ladder_type = team.gender

    try:
        if team.holiday_mode_active:
            team.holiday_mode_active = False
            team.holiday_mode_end = datetime.now()
            action = "deactivated"

            email_body = f"""Hi {team.player1_name},

HOLIDAY MODE DEACTIVATED

An administrator has deactivated holiday mode for your team.

Team: {team.team_name}
Division: {ladder_type.capitalize()} Ladder
Current Rank: #{team.current_rank}
Status: Now AVAILABLE for challenges

You can now be challenged by other teams again.

- BD Padel League
"""

        else:
            active_challenges = LadderChallenge.query.filter(
                db.or_(
                    LadderChallenge.challenger_team_id == team_id,
                    LadderChallenge.challenged_team_id == team_id
                ),
                LadderChallenge.status.in_(['pending_acceptance', 'accepted'])
            ).count()

            if active_challenges > 0:
                flash(f"Cannot activate holiday mode - team has {active_challenges} active challenge(s)", "error")
                return redirect(url_for('admin_ladder_rankings', ladder_type=ladder_type))

            team.holiday_mode_active = True
            team.holiday_mode_start = datetime.now()
            team.holiday_mode_end = None
            action = "activated"

            email_body = f"""Hi {team.player1_name},

HOLIDAY MODE ACTIVATED

An administrator has activated holiday mode for your team.

Team: {team.team_name}
Division: {ladder_type.capitalize()} Ladder
Current Rank: #{team.current_rank}
Status: Now ON HOLIDAY (cannot be challenged)

While on holiday mode, you cannot be challenged by other teams and your rank is protected.

- BD Padel League
"""

        db.session.commit()

        if team.contact_preference_email:
            if team.player1_email:
                send_email_notification(team.player1_email, f"Holiday Mode {action.capitalize()}", email_body)
            if team.player2_email and team.player2_email != team.player1_email:
                send_email_notification(team.player2_email, f"Holiday Mode {action.capitalize()}", email_body)

        flash(f"Holiday mode {action} for '{team.team_name}'", "success")
        return redirect(url_for('admin_ladder_rankings', ladder_type=ladder_type))

    except Exception as e:
        db.session.rollback()
        flash(f"Error toggling holiday mode: {str(e)}", "error")
        return redirect(url_for('admin_ladder_rankings', ladder_type=ladder_type))


@app.route("/admin/settings", methods=["GET", "POST"])
@require_admin_auth
def admin_settings():
    """Admin settings page for league configuration"""
    # Get or create settings
    settings = LeagueSettings.query.first()
    if not settings:
        settings = LeagueSettings(swiss_rounds_count=5, playoff_teams_count=8, team_registration_open=True, freeagent_registration_open=True)
        db.session.add(settings)
        db.session.commit()

    if request.method == "POST":
        try:
            # Update settings
            swiss_rounds = request.form.get("swiss_rounds_count", type=int)
            playoff_teams = request.form.get("playoff_teams_count", type=int)
            team_reg_open = request.form.get("team_registration_open") == "on"
            freeagent_reg_open = request.form.get("freeagent_registration_open") == "on"

            # Validation
            if swiss_rounds and swiss_rounds < 1:
                flash("Swiss rounds must be at least 1", "error")
                return redirect(url_for("admin_settings"))

            if playoff_teams and playoff_teams not in [4, 8]:
                flash("Playoff teams must be 4 or 8", "error")
                return redirect(url_for("admin_settings"))

            # Only allow changes if playoffs haven't started
            if settings.current_phase != "swiss":
                flash("Cannot change settings - playoffs have already started!", "error")
                return redirect(url_for("admin_settings"))

            # Update settings
            if swiss_rounds:
                settings.swiss_rounds_count = swiss_rounds
            if playoff_teams:
                settings.playoff_teams_count = playoff_teams

            # Update registration toggles (always update these)
            settings.team_registration_open = team_reg_open
            settings.freeagent_registration_open = freeagent_reg_open

            db.session.commit()
            flash("✅ League settings updated successfully!", "success")
            return redirect(url_for("admin_settings"))

        except Exception as e:
            flash(f"Error updating settings: {str(e)}", "error")
            return redirect(url_for("admin_settings"))

    return render_template("admin_settings.html", settings=settings)


@app.route("/admin/ladder/settings", methods=["GET", "POST"])
@require_admin_auth
def admin_ladder_settings():
    """Admin settings page for ladder configuration"""
    settings = LadderSettings.query.first()
    if not settings:
        settings = LadderSettings(
            challenge_acceptance_hours=48,
            max_challenge_rank_difference=3,
            acceptance_penalty_ranks=1,
            match_completion_days=7,
            completion_penalty_ranks=1,
            holiday_mode_grace_weeks=2,
            holiday_mode_weekly_penalty_ranks=1,
            min_matches_per_month=2,
            inactivity_penalty_ranks=3,
            no_show_penalty_ranks=1,
            men_registration_open=True,
            women_registration_open=True
        )
        db.session.add(settings)
        db.session.commit()

    if request.method == "POST":
        try:
            challenge_acceptance_hours = request.form.get("challenge_acceptance_hours", type=int)
            max_challenge_rank_difference = request.form.get("max_challenge_rank_difference", type=int)
            acceptance_penalty_ranks = request.form.get("acceptance_penalty_ranks", type=int)
            match_completion_days = request.form.get("match_completion_days", type=int)
            completion_penalty_ranks = request.form.get("completion_penalty_ranks", type=int)
            holiday_mode_grace_weeks = request.form.get("holiday_mode_grace_weeks", type=int)
            holiday_mode_weekly_penalty_ranks = request.form.get("holiday_mode_weekly_penalty_ranks", type=int)
            min_matches_per_month = request.form.get("min_matches_per_month", type=int)
            inactivity_penalty_ranks = request.form.get("inactivity_penalty_ranks", type=int)
            no_show_penalty_ranks = request.form.get("no_show_penalty_ranks", type=int)
            men_registration_open = request.form.get("men_registration_open") == "on"
            women_registration_open = request.form.get("women_registration_open") == "on"
            penalties_active = request.form.get("penalties_active") == "on"

            if challenge_acceptance_hours and challenge_acceptance_hours <= 0:
                flash("Challenge acceptance hours must be greater than 0", "error")
                return redirect(url_for("admin_ladder_settings"))

            if max_challenge_rank_difference and max_challenge_rank_difference <= 0:
                flash("Max challenge rank difference must be greater than 0", "error")
                return redirect(url_for("admin_ladder_settings"))

            if acceptance_penalty_ranks is not None and acceptance_penalty_ranks < 0:
                flash("Acceptance penalty ranks cannot be negative", "error")
                return redirect(url_for("admin_ladder_settings"))

            if match_completion_days and match_completion_days <= 0:
                flash("Match completion days must be greater than 0", "error")
                return redirect(url_for("admin_ladder_settings"))

            if completion_penalty_ranks is not None and completion_penalty_ranks < 0:
                flash("Completion penalty ranks cannot be negative", "error")
                return redirect(url_for("admin_ladder_settings"))

            if holiday_mode_grace_weeks is not None and holiday_mode_grace_weeks < 0:
                flash("Holiday mode grace weeks cannot be negative", "error")
                return redirect(url_for("admin_ladder_settings"))

            if holiday_mode_weekly_penalty_ranks is not None and holiday_mode_weekly_penalty_ranks < 0:
                flash("Holiday mode weekly penalty cannot be negative", "error")
                return redirect(url_for("admin_ladder_settings"))

            if min_matches_per_month is not None and min_matches_per_month < 0:
                flash("Minimum matches per month cannot be negative", "error")
                return redirect(url_for("admin_ladder_settings"))

            if inactivity_penalty_ranks is not None and inactivity_penalty_ranks < 0:
                flash("Inactivity penalty ranks cannot be negative", "error")
                return redirect(url_for("admin_ladder_settings"))

            if no_show_penalty_ranks is not None and no_show_penalty_ranks < 0:
                flash("No-show penalty ranks cannot be negative", "error")
                return redirect(url_for("admin_ladder_settings"))

            if challenge_acceptance_hours:
                settings.challenge_acceptance_hours = challenge_acceptance_hours
            if max_challenge_rank_difference:
                settings.max_challenge_rank_difference = max_challenge_rank_difference
            if acceptance_penalty_ranks is not None:
                settings.acceptance_penalty_ranks = acceptance_penalty_ranks
            if match_completion_days:
                settings.match_completion_days = match_completion_days
            if completion_penalty_ranks is not None:
                settings.completion_penalty_ranks = completion_penalty_ranks
            if holiday_mode_grace_weeks is not None:
                settings.holiday_mode_grace_weeks = holiday_mode_grace_weeks
            if holiday_mode_weekly_penalty_ranks is not None:
                settings.holiday_mode_weekly_penalty_ranks = holiday_mode_weekly_penalty_ranks
            if min_matches_per_month is not None:
                settings.min_matches_per_month = min_matches_per_month
            if inactivity_penalty_ranks is not None:
                settings.inactivity_penalty_ranks = inactivity_penalty_ranks
            if no_show_penalty_ranks is not None:
                settings.no_show_penalty_ranks = no_show_penalty_ranks

            settings.men_registration_open = men_registration_open
            settings.women_registration_open = women_registration_open
            settings.penalties_active = penalties_active

            db.session.commit()
            flash("✅ Ladder settings updated successfully!", "success")
            return redirect(url_for("admin_ladder_settings"))

        except Exception as e:
            db.session.rollback()
            flash(f"Error updating ladder settings: {str(e)}", "error")
            return redirect(url_for("admin_ladder_settings"))

    return render_template("admin_ladder_settings.html", settings=settings)


@app.route("/admin/ladder/americano/tournaments")
@require_admin_auth
def admin_americano_tournaments():
    """List all Americano tournaments"""
    from datetime import datetime

    try:
        tournaments = AmericanoTournament.query.order_by(AmericanoTournament.tournament_date.desc()).all()

        tournament_data = []
        for tournament in tournaments:
            participating_ids = []
            if tournament.participating_free_agents:
                import json
                try:
                    participating_ids = json.loads(tournament.participating_free_agents)
                except:
                    pass

            participants_count = len(participating_ids)

            matches = AmericanoMatch.query.filter_by(tournament_id=tournament.id).all()
            matches_count = len(matches)
            completed_matches = len([m for m in matches if m.status == 'completed'])

            tournament_data.append({
                'tournament': tournament,
                'participants_count': participants_count,
                'matches_count': matches_count,
                'completed_matches': completed_matches
            })

        response = make_response(render_template("admin_americano_tournaments.html", tournament_data=tournament_data))
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response

    except Exception as e:
        app.logger.error(f"Error loading Americano tournaments: {str(e)}")
        flash(f"Error loading tournaments: {str(e)}", "error")
        return redirect(url_for('admin'))


@app.route("/admin/ladder/americano/create", methods=["GET", "POST"])
@require_admin_auth
def admin_americano_create():
    """Create a new Americano tournament"""
    from datetime import datetime
    import json
    import secrets
    from utils import send_email_notification, normalize_team_name
    from collections import defaultdict

    if request.method == "POST":
        try:
            gender = request.form.get("gender")
            tournament_date_str = request.form.get("tournament_date")
            location = request.form.get("location", "")
            participant_ids = request.form.getlist("participants")
            points_per_match = request.form.get("points_per_match", type=int, default=24)
            time_limit_minutes = request.form.get("time_limit_minutes", type=int, default=20)
            serves_before_rotation = request.form.get("serves_before_rotation", type=int, default=2)

            if not gender or not tournament_date_str:
                flash("Gender and tournament date are required", "error")
                return redirect(url_for("admin_americano_create"))

            if len(participant_ids) < 4:
                flash("At least 4 participants are required for Americano tournament", "error")
                return redirect(url_for("admin_americano_create"))

            # Validate format settings
            if points_per_match not in [16, 24, 32]:
                flash("Points per match must be 16, 24, or 32", "error")
                return redirect(url_for("admin_americano_create"))

            if time_limit_minutes not in [10, 20]:
                flash("Time limit must be 10 or 20 minutes", "error")
                return redirect(url_for("admin_americano_create"))

            if serves_before_rotation not in [2, 4]:
                flash("Serves rotation must be 2 or 4", "error")
                return redirect(url_for("admin_americano_create"))

            tournament_date = datetime.strptime(tournament_date_str, "%Y-%m-%d")

            tournament = AmericanoTournament(
                tournament_date=tournament_date,
                gender=gender,
                location=location,
                status="setup",
                scoring_format="points",
                points_per_match=points_per_match,
                time_limit_minutes=time_limit_minutes,
                serves_before_rotation=serves_before_rotation,
                participating_free_agents=json.dumps([int(p) for p in participant_ids]),
                created_at=datetime.now()
            )

            db.session.add(tournament)
            db.session.commit()

            from utils import send_email_notification
            for participant_id in participant_ids:
                free_agent = LadderFreeAgent.query.get(int(participant_id))
                if free_agent and free_agent.email:
                    subject = f"🎾 Americano Tournament Invitation - {gender.title()}'s Division"
                    body = f"""Hi {free_agent.name},

You've been invited to participate in an Americano Tournament!

Tournament Details:
📅 Date: {tournament_date.strftime('%B %d, %Y')}
📍 Location: {location or 'TBD'}
🏆 Division: {gender.title()}'s

What is Americano Format?
- Multiple rounds of doubles matches
- Partners rotate each round
- Everyone plays with everyone
- Fun, social, and competitive!

Match schedule will be sent soon. Get ready to play!

- BD Padel League
"""
                    send_email_notification(free_agent.email, subject, body)

            flash(f"✅ Tournament created successfully! {len(participant_ids)} invitations sent.", "success")
            return redirect(url_for("admin_americano_detail", tournament_id=tournament.id))

        except Exception as e:
            db.session.rollback()
            flash(f"Error creating tournament: {str(e)}", "error")
            return redirect(url_for("admin_americano_create"))

    men_agents = LadderFreeAgent.query.filter_by(gender="men").all()
    women_agents = LadderFreeAgent.query.filter_by(gender="women").all()

    return render_template("admin_americano_create.html", 
                         men_agents=men_agents, 
                         women_agents=women_agents)


@app.route("/admin/ladder/americano/<int:tournament_id>")
@require_admin_auth
def admin_americano_detail(tournament_id):
    """View tournament details"""
    import json

    tournament = AmericanoTournament.query.get_or_404(tournament_id)

    participant_ids = []
    if tournament.participating_free_agents:
        try:
            participant_ids = json.loads(tournament.participating_free_agents)
        except:
            pass

    participants = []
    for pid in participant_ids:
        agent = LadderFreeAgent.query.get(pid)
        if agent:
            participants.append(agent)

    matches = AmericanoMatch.query.filter_by(tournament_id=tournament_id).order_by(
        AmericanoMatch.round_number, 
        AmericanoMatch.id
    ).all()

    matches_by_round = {}
    for match in matches:
        if match.round_number not in matches_by_round:
            matches_by_round[match.round_number] = []

        p1 = LadderFreeAgent.query.get(match.player1_id)
        p2 = LadderFreeAgent.query.get(match.player2_id)
        p3 = LadderFreeAgent.query.get(match.player3_id)
        p4 = LadderFreeAgent.query.get(match.player4_id)

        matches_by_round[match.round_number].append({
            'match': match,
            'p1': p1,
            'p2': p2,
            'p3': p3,
            'p4': p4
        })

    return render_template("admin_americano_detail.html",
                         tournament=tournament,
                         participants=participants,
                         matches_by_round=matches_by_round,
                         total_rounds=tournament.total_rounds)


@app.route("/admin/ladder/americano/<int:tournament_id>/generate-matches", methods=["POST"])
@require_admin_auth
def admin_americano_generate_matches(tournament_id):
    """Generate Americano matches using the pairing algorithm"""
    from datetime import datetime
    import json
    from utils import generate_americano_pairings, send_email_notification

    tournament = AmericanoTournament.query.get_or_404(tournament_id)

    existing_matches = AmericanoMatch.query.filter_by(tournament_id=tournament_id).all()
    if existing_matches:
        flash("⚠️ Matches already generated for this tournament. Delete existing matches first if you want to regenerate.", "error")
        return redirect(url_for("admin_americano_detail", tournament_id=tournament_id))

    try:
        participant_ids = []
        if tournament.participating_free_agents:
            participant_ids = json.loads(tournament.participating_free_agents)

        if len(participant_ids) < 4:
            flash("Need at least 4 participants to generate matches", "error")
            return redirect(url_for("admin_americano_detail", tournament_id=tournament_id))

        rounds = generate_americano_pairings(participant_ids)

        if not rounds:
            flash("Could not generate pairings", "error")
            return redirect(url_for("admin_americano_detail", tournament_id=tournament_id))

        total_matches_created = 0
        for round_num, round_matches in enumerate(rounds, start=1):
            for court_num, match_tuple in enumerate(round_matches, start=1):
                p1_id, p2_id, p3_id, p4_id = match_tuple

                match = AmericanoMatch(
                    tournament_id=tournament_id,
                    round_number=round_num,
                    court_number=court_num,
                    player1_id=p1_id,
                    player2_id=p2_id,
                    player3_id=p3_id,
                    player4_id=p4_id,
                    status="pending",
                    created_at=datetime.now()
                )
                db.session.add(match)
                total_matches_created += 1

        tournament.total_rounds = len(rounds)
        tournament.status = "in_progress"
        db.session.commit()

        for participant_id in participant_ids:
            free_agent = LadderFreeAgent.query.get(participant_id)
            if free_agent and free_agent.email:
                subject = f"🎾 Americano Tournament Schedule - {tournament.gender.title()}'s Division"
                body = f"""Hi {free_agent.name},

You've been invited to participate in an Americano Tournament!

Tournament Details:
📅 Date: {tournament.tournament_date.strftime('%B %d, %Y')}
📍 Location: {tournament.location or 'TBD'}
🏆 Division: {tournament.gender.title()}'s

What is Americano Format?
- Multiple rounds of doubles matches
- Partners rotate each round
- Everyone plays with everyone
- Fun, social, and competitive!

Match schedule will be sent soon. Get ready to play!

- BD Padel League
"""
                send_email_notification(free_agent.email, subject, body)

        flash(f"✅ Successfully generated {total_matches_created} matches across {len(rounds)} rounds! Schedule emails sent to all participants.", "success")
        return redirect(url_for("admin_americano_detail", tournament_id=tournament_id))

    except Exception as e:
        db.session.rollback()
        flash(f"Error generating matches: {str(e)}", "error")
        return redirect(url_for("admin_americano_detail", tournament_id=tournament_id))


@app.route("/admin/ladder/americano/<int:tournament_id>/scores", methods=["GET", "POST"])
@require_admin_auth
def admin_americano_scores(tournament_id):
    """Enter scores for Americano matches"""
    from datetime import datetime
    import json

    tournament = AmericanoTournament.query.get_or_404(tournament_id)

    if request.method == "POST":
        try:
            match_id = request.form.get("match_id", type=int)
            team_a_score = request.form.get("team_a_score", type=int)
            team_b_score = request.form.get("team_b_score", type=int)

            if not match_id or team_a_score is None or team_b_score is None:
                flash("Match ID and scores are required", "error")
                return redirect(url_for("admin_americano_scores", tournament_id=tournament_id))

            match = AmericanoMatch.query.get(match_id)
            if not match or match.tournament_id != tournament_id:
                flash("Invalid match", "error")
                return redirect(url_for("admin_americano_scores", tournament_id=tournament_id))

            # Validate scores
            if team_a_score < 0 or team_b_score < 0:
                flash("Scores cannot be negative", "error")
                return redirect(url_for("admin_americano_scores", tournament_id=tournament_id))

            # Maximum validation: points_per_match + 10% buffer
            max_allowed = int(tournament.points_per_match * 1.1)
            if team_a_score > max_allowed or team_b_score > max_allowed:
                flash(f"Individual scores cannot exceed {max_allowed} (10% buffer over {tournament.points_per_match})", "error")
                return redirect(url_for("admin_americano_scores", tournament_id=tournament_id))

            # Points-based scoring: each player gets their team's score
            match.score_team_a = team_a_score
            match.score_team_b = team_b_score

            # Each player receives points equal to their team's score
            match.points_player1 = team_a_score  # Team A Player 1
            match.points_player2 = team_a_score  # Team A Player 2
            match.points_player3 = team_b_score  # Team B Player 3
            match.points_player4 = team_b_score  # Team B Player 4

            match.status = "completed"
            db.session.commit()

            flash(f"✅ Points recorded: Team A ({team_a_score}) vs Team B ({team_b_score}). Each player receives their team's points.", "success")
            return redirect(url_for("admin_americano_scores", tournament_id=tournament_id))

        except Exception as e:
            db.session.rollback()
            flash(f"Error recording score: {str(e)}", "error")
            return redirect(url_for("admin_americano_scores", tournament_id=tournament_id))

    participant_ids = []
    if tournament.participating_free_agents:
        participant_ids = json.loads(tournament.participating_free_agents)

    participants = []
    for pid in participant_ids:
        agent = LadderFreeAgent.query.get(pid)
        if agent:
            participants.append(agent)

    matches = AmericanoMatch.query.filter_by(tournament_id=tournament_id).order_by(
        AmericanoMatch.round_number, 
        AmericanoMatch.id
    ).all()

    matches_by_round = {}
    for match in matches:
        if match.round_number not in matches_by_round:
            matches_by_round[match.round_number] = []

        p1 = LadderFreeAgent.query.get(match.player1_id)
        p2 = LadderFreeAgent.query.get(match.player2_id)
        p3 = LadderFreeAgent.query.get(match.player3_id)
        p4 = LadderFreeAgent.query.get(match.player4_id)

        matches_by_round[match.round_number].append({
            'match': match,
            'p1': p1,
            'p2': p2,
            'p3': p3,
            'p4': p4
        })

    return render_template("admin_americano_scores.html",
                         tournament=tournament,
                         participants=participants,
                         matches_by_round=matches_by_round)


@app.route("/admin/ladder/americano/<int:tournament_id>/leaderboard")
@require_admin_auth
def admin_americano_leaderboard(tournament_id):
    """View tournament leaderboard"""
    import json
    from collections import defaultdict

    tournament = AmericanoTournament.query.get_or_404(tournament_id)

    participant_ids = []
    if tournament.participating_free_agents:
        participant_ids = json.loads(tournament.participating_free_agents)

    player_stats = defaultdict(lambda: {
        'player': None,
        'matches_played': 0,
        'wins': 0,
        'losses': 0,
        'draws': 0,
        'total_points': 0
    })

    for pid in participant_ids:
        agent = LadderFreeAgent.query.get(pid)
        if agent:
            player_stats[pid]['player'] = agent

    matches = AmericanoMatch.query.filter_by(tournament_id=tournament_id, status='completed').all()

    for match in matches:
        for player_id in [match.player1_id, match.player2_id, match.player3_id, match.player4_id]:
            if player_id in player_stats:
                player_stats[player_id]['matches_played'] += 1

                if player_id == match.player1_id:
                    points = match.points_player1
                elif player_id == match.player2_id:
                    points = match.points_player2
                elif player_id == match.player3_id:
                    points = match.points_player3
                else:
                    points = match.points_player4

                player_stats[player_id]['total_points'] += points
                if points == 3:
                    player_stats[player_id]['wins'] += 1
                elif points == 1:
                    player_stats[player_id]['draws'] += 1
                else:
                    player_stats[player_id]['losses'] += 1

    leaderboard = sorted(
        player_stats.values(),
        key=lambda x: (x['total_points'], x['wins']),
        reverse=True
    )

    total_players = len(leaderboard)
    top_50_percent_count = max(1, total_players // 2)

    for idx, entry in enumerate(leaderboard, start=1):
        entry['rank'] = idx
        entry['is_eligible'] = (idx <= top_50_percent_count)

    all_matches_completed = AmericanoMatch.query.filter_by(
        tournament_id=tournament_id, 
        status='pending'
    ).count() == 0

    if all_matches_completed and tournament.status != 'completed':
        tournament.status = 'completed'
        tournament.completed_at = datetime.now()
        db.session.commit()

    return render_template("admin_americano_leaderboard.html",
                         tournament=tournament,
                         leaderboard=leaderboard,
                         top_50_percent_count=top_50_percent_count)


@app.route("/admin/ladder/americano/<int:tournament_id>/pair-agents", methods=["GET", "POST"])
@require_admin_auth
def admin_americano_pair_agents(tournament_id):
    """Pair tournament winners into ladder teams"""
    from datetime import datetime
    import json
    import secrets
    from utils import send_email_notification
    from collections import defaultdict

    tournament = AmericanoTournament.query.get_or_404(tournament_id)

    if request.method == "POST":
        try:
            pairs = []
            pair_index = 0
            while True:
                player1_id = request.form.get(f"player1_{pair_index}", type=int)
                player2_id = request.form.get(f"player2_{pair_index}", type=int)
                team_name = request.form.get(f"team_name_{pair_index}")

                if not player1_id or not player2_id or not team_name:
                    break

                pairs.append({
                    'player1_id': player1_id,
                    'player2_id': player2_id,
                    'team_name': team_name
                })
                pair_index += 1

            if not pairs:
                flash("No pairs selected", "error")
                return redirect(url_for("admin_americano_pair_agents", tournament_id=tournament_id))

            max_rank = db.session.query(db.func.max(LadderTeam.current_rank)).filter_by(
                gender=tournament.gender
            ).scalar() or 0

            for pair_data in pairs:
                player1 = LadderFreeAgent.query.get(pair_data['player1_id'])
                player2 = LadderFreeAgent.query.get(pair_data['player2_id'])

                if not player1 or not player2:
                    continue

                max_rank += 1

                team = LadderTeam(
                    team_name=pair_data['team_name'],
                    team_name_canonical=normalize_team_name(pair_data['team_name']),
                    player1_name=player1.name,
                    player1_phone=player1.phone,
                    player1_email=player1.email,
                    player2_name=player2.name,
                    player2_phone=player2.phone,
                    player2_email=player2.email,
                    gender=tournament.gender,
                    ladder_type=tournament.gender,
                    current_rank=max_rank,
                    access_token=secrets.token_urlsafe(32),
                    created_at=datetime.now(),
                    updated_at=datetime.now()
                )

                db.session.add(team)

                db.session.delete(player1)
                db.session.delete(player2)

                for player, partner_name in [(player1, player2.name), (player2, player1.name)]:
                    if player.email:
                        subject = f"🎉 Congratulations! You've been paired into the {tournament.gender.title()}'s Ladder"
                        body = f"""Hi {player.name},

Congratulations on completing the Americano Tournament!

🏆 You've been paired with {partner_name} to form the team: {pair_data['team_name']}

Team Details:
📊 Starting Rank: #{max_rank}
🪜 Division: {tournament.gender.title()}'s Ladder
🎾 Ready to challenge teams above you!

Your team has been added to the bottom of the ladder. You can now:
1. Challenge teams ranked above you (up to 3 positions)
2. Accept challenges from teams below you
3. Climb the ladder through victories!

Welcome to the ladder! Let's see how high you can climb! 🚀

- BD Padel League
"""
                        send_email_notification(player.email, subject, body)

            db.session.commit()

            flash(f"✅ Successfully created {len(pairs)} new teams from tournament participants! Congratulations emails sent.", "success")
            return redirect(url_for("admin_americano_leaderboard", tournament_id=tournament_id))

        except Exception as e:
            db.session.rollback()
            flash(f"Error creating teams: {str(e)}", "error")
            return redirect(url_for("admin_americano_pair_agents", tournament_id=tournament_id))

    participant_ids = []
    if tournament.participating_free_agents:
        participant_ids = json.loads(tournament.participating_free_agents)

    player_stats = defaultdict(lambda: {
        'player': None,
        'total_points': 0,
        'matches_played': 0,
        'wins': 0
    })

    for pid in participant_ids:
        agent = LadderFreeAgent.query.get(pid)
        if agent:
            player_stats[pid]['player'] = agent

    matches = AmericanoMatch.query.filter_by(tournament_id=tournament_id, status='completed').all()

    for match in matches:
        for player_id in [match.player1_id, match.player2_id, match.player3_id, match.player4_id]:
            if player_id in player_stats:
                player_stats[player_id]['matches_played'] += 1

                if player_id == match.player1_id:
                    points = match.points_player1
                elif player_id == match.player2_id:
                    points = match.points_player2
                elif player_id == match.player3_id:
                    points = match.points_player3
                else:
                    points = match.points_player4

                player_stats[player_id]['total_points'] += points
                if points == 3:
                    player_stats[player_id]['wins'] += 1

    ranked_players = sorted(
        [(pid, stats) for pid, stats in player_stats.items() if stats['player']],
        key=lambda x: (x[1]['total_points'], x[1]['wins']),
        reverse=True
    )

    total_players = len(ranked_players)
    top_50_percent_count = max(1, total_players // 2)

    eligible_players = []
    all_players = []

    for idx, (pid, stats) in enumerate(ranked_players, start=1):
        entry = {
            'rank': idx,
            'player': stats['player'],
            'total_points': stats['total_points'],
            'is_eligible': (idx <= top_50_percent_count)
        }
        all_players.append(entry)
        if entry['is_eligible']:
            eligible_players.append(entry)

    return render_template("admin_americano_pair_agents.html",
                         tournament=tournament,
                         eligible_players=eligible_players,
                         all_players=all_players,
                         top_50_percent_count=top_50_percent_count)


@app.route("/admin/send-mass-email", methods=["GET", "POST"])
@require_admin_auth
def send_mass_email():
    """Mass email communication feature for admin"""
    if request.method == "GET":
        teams = Team.query.all()
        free_agents = FreeAgent.query.all()

        team_emails = []
        for team in teams:
            if team.player1_email:
                team_emails.append(team.player1_email)
            if team.player2_email:
                team_emails.append(team.player2_email)

        free_agent_emails = [fa.email for fa in free_agents if fa.email]

        team_count = len([e for e in team_emails if e])
        free_agent_count = len([e for e in free_agent_emails if e])
        both_count = len(set([e for e in team_emails + free_agent_emails if e]))

        return render_template(
            "admin_mass_email.html",
            team_count=team_count,
            free_agent_count=free_agent_count,
            both_count=both_count
        )

    try:
        subject = request.form.get("subject", "").strip()
        message = request.form.get("message", "").strip()
        recipient_type = request.form.get("recipient_type", "")

        if not subject or not message:
            flash("Subject and message are required", "error")
            return redirect(url_for("send_mass_email"))

        if recipient_type not in ["teams", "free_agents", "both"]:
            flash("Invalid recipient selection", "error")
            return redirect(url_for("send_mass_email"))

        from utils import send_email_notification

        recipients = []

        if recipient_type in ["teams", "both"]:
            teams = Team.query.all()
            for team in teams:
                if team.player1_email:
                    recipients.append(team.player1_email)
                if team.player2_email and team.player2_email != team.player1_email:
                    recipients.append(team.player2_email)

        if recipient_type in ["free_agents", "both"]:
            free_agents = FreeAgent.query.all()
            for fa in free_agents:
                if fa.email and fa.email not in recipients:
                    recipients.append(fa.email)

        recipients = list(set([r for r in recipients if r]))

        if not recipients:
            flash("No recipients found with email addresses", "error")
            return redirect(url_for("send_mass_email"))

        sent_count = 0
        failed_count = 0

        for recipient in recipients:
            if send_email_notification(recipient, subject, message):
                sent_count += 1
            else:
                failed_count += 1

        if sent_count > 0:
            flash(f"✅ Successfully sent {sent_count} email(s)", "success")
        if failed_count > 0:
            flash(f"⚠️ Failed to send {failed_count} email(s)", "warning")

        return redirect(url_for("send_mass_email"))

    except Exception as e:
        flash(f"Error sending emails: {str(e)}", "error")
        return redirect(url_for("send_mass_email"))


@app.route("/admin/generate-playoff-preview", methods=["POST"])
@require_admin_auth
def generate_playoff_preview_route():
    """Generate playoff preview and transition to playoff_preview phase"""
    import json

    # Check if Swiss is complete
    swiss_complete, _, _ = check_swiss_completion()
    if not swiss_complete:
        flash("Cannot generate playoffs - Swiss rounds are not complete yet!", "error")
        return redirect(url_for("admin_panel"))

    # Get or create settings
    settings = LeagueSettings.query.first()
    if not settings:
        settings = LeagueSettings(swiss_rounds_count=5, playoff_teams_count=8)
        db.session.add(settings)
        db.session.commit()

    # Check if playoffs already approved
    if settings.playoffs_approved:
        flash("Playoffs have already been approved!", "warning")
        return redirect(url_for("admin_panel"))

    # Generate preview
    preview_data = generate_playoff_preview()
    if not preview_data:
        flash("Error generating playoff preview", "error")
        return redirect(url_for("admin_panel"))

    # Save qualified team IDs to settings
    qualified_ids = [team_data['team'].id for team_data in preview_data['qualified_teams']]
    settings.qualified_team_ids = json.dumps(qualified_ids)
    settings.current_phase = "playoff_preview"
    db.session.commit()

    flash(f"✅ Playoff preview generated! Top {len(qualified_ids)} teams have qualified. Please review and approve.", "success")
    return redirect(url_for("playoff_approval_page"))


@app.route("/admin/playoff-approval")
@require_admin_auth
def playoff_approval_page():
    """Show playoff approval page with Top 8 teams and bracket preview"""
    import json

    settings = LeagueSettings.query.first()
    if not settings or settings.current_phase != "playoff_preview":
        flash("No playoff preview available", "warning")
        return redirect(url_for("admin_panel"))

    # Get qualified team IDs
    if not settings.qualified_team_ids:
        flash("No qualified teams found", "error")
        return redirect(url_for("admin_panel"))

    team_ids = json.loads(settings.qualified_team_ids)

    # Get team objects and build qualified teams list
    qualified_teams = []
    for idx, team_id in enumerate(team_ids, start=1):
        team = Team.query.get(team_id)
        if team:
            qualified_teams.append({
                'team': team,
                'seed': idx,
                'points': team.points,
                'sets_diff': team.sets_diff,
                'games_diff': team.games_diff
            })

    # Build bracket preview
    bracket_preview = []
    if len(qualified_teams) >= 8:
        bracket_preview = [
            {'match': 'QF1', 'seed1': 1, 'team1': qualified_teams[0]['team'].team_name, 'seed8': 8, 'team8': qualified_teams[7]['team'].team_name},
            {'match': 'QF2', 'seed2': 2, 'team2': qualified_teams[1]['team'].team_name, 'seed7': 7, 'team7': qualified_teams[6]['team'].team_name},
            {'match': 'QF3', 'seed3': 3, 'team3': qualified_teams[2]['team'].team_name, 'seed6': 6, 'team6': qualified_teams[5]['team'].team_name},
            {'match': 'QF4', 'seed4': 4, 'team4': qualified_teams[3]['team'].team_name, 'seed5': 5, 'team5': qualified_teams[4]['team'].team_name},
        ]
    elif len(qualified_teams) >= 4:
        bracket_preview = [
            {'match': 'SF1', 'seed1': 1, 'team1': qualified_teams[0]['team'].team_name, 'seed4': 4, 'team4': qualified_teams[3]['team'].team_name},
            {'match': 'SF2', 'seed2': 2, 'team2': qualified_teams[1]['team'].team_name, 'seed3': 3, 'team3': qualified_teams[2]['team'].team_name},
        ]

    return render_template(
        "playoff_approval.html",
        qualified_teams=qualified_teams,
        bracket_preview=bracket_preview,
        settings=settings
    )


@app.route("/admin/approve-playoffs", methods=["POST"])
@require_admin_auth
def approve_playoffs():
    """Approve playoffs and generate quarterfinals"""
    settings = LeagueSettings.query.first()
    if not settings or settings.current_phase != "playoff_preview":
        flash("Cannot approve playoffs at this time", "error")
        return redirect(url_for("admin_panel"))

    # Mark playoffs as approved
    settings.playoffs_approved = True
    settings.current_phase = "playoffs"
    db.session.commit()

    flash("✅ Playoffs approved! You can now generate playoff rounds.", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/reject-playoffs", methods=["POST"])
@require_admin_auth
def reject_playoffs():
    """Reject playoff preview and return to Swiss phase"""
    settings = LeagueSettings.query.first()
    if not settings:
        flash("Settings not found", "error")
        return redirect(url_for("admin_panel"))

    # Reset to Swiss phase
    settings.current_phase = "swiss"
    settings.qualified_team_ids = None
    settings.playoffs_approved = False
    db.session.commit()

    flash("Playoff preview rejected. You can regenerate it when ready.", "info")
    return redirect(url_for("admin_panel"))


@app.route("/admin/generate-next-knockout-round", methods=["POST"])
@require_admin_auth
def generate_next_knockout_round():
    """Generate the next knockout round (SF after QF, Final after SF)"""
    try:
        phase = request.form.get("phase")  # "semifinal" or "final"
        round_deadline_str = request.form.get("round_deadline")
        
        # Parse deadline string to datetime, normalized to end-of-day (23:59:59)
        from datetime import datetime, time as dt_time
        round_deadline = None
        if round_deadline_str:
            try:
                deadline_date = datetime.strptime(round_deadline_str, "%Y-%m-%d").date()
                round_deadline = datetime.combine(deadline_date, dt_time(23, 59, 59))
            except ValueError:
                flash("Invalid deadline date format", "error")
                return redirect(url_for("admin_panel"))
        
        if phase not in ["semifinal", "final"]:
            flash("Invalid knockout phase", "error")
            return redirect(url_for("admin_panel"))
        
        settings = LeagueSettings.query.first()
        if not settings:
            flash("Settings not found", "error")
            return redirect(url_for("admin_panel"))
        
        # Determine round number based on phase
        if phase == "semifinal":
            round_number = settings.swiss_rounds_count + 2  # Round 7 for 5 Swiss rounds
        else:  # final
            round_number = settings.swiss_rounds_count + 3  # Round 8 for 5 Swiss rounds
        
        # Check if matches already exist for this phase
        existing_matches = Match.query.filter_by(phase=phase).first()
        if existing_matches:
            flash(f"{phase.title()} matches already exist!", "error")
            return redirect(url_for("admin_panel"))
        
        # Validate prerequisites
        if phase == "semifinal":
            # Check all QF matches are complete
            qf_matches = Match.query.filter_by(phase="quarterfinal").all()
            if not qf_matches or not all(m.winner_id for m in qf_matches):
                flash("Cannot generate Semi-Finals: Quarter-Finals are not complete", "error")
                return redirect(url_for("admin_panel"))
        elif phase == "final":
            # Check all SF matches are complete
            sf_matches = Match.query.filter_by(phase="semifinal").all()
            if not sf_matches or not all(m.winner_id for m in sf_matches):
                flash("Cannot generate Finals: Semi-Finals are not complete", "error")
                return redirect(url_for("admin_panel"))
        
        # Generate the knockout round
        from utils import generate_playoff_bracket
        matches = generate_playoff_bracket(round_number, phase)
        
        if not matches:
            flash(f"Could not generate {phase} matches", "error")
            return redirect(url_for("admin_panel"))
        
        # Set deadline on all generated matches
        if round_deadline:
            for match in matches:
                match.round_deadline = round_deadline
            db.session.commit()
        
        phase_names = {"semifinal": "Semi-Finals", "final": "Finals"}
        flash(f"✅ {phase_names.get(phase, phase.title())} generated with {len(matches)} match(es)!", "success")
        return redirect(url_for("admin_panel"))
        
    except Exception as e:
        logging.error(f"Error generating knockout round: {str(e)}")
        flash(f"Error generating knockout round: {str(e)}", "error")
        return redirect(url_for("admin_panel"))


@app.route("/admin/generate-round", methods=["POST"])
@require_admin_auth
def generate_round():
    """Generate Swiss-format round pairings as DRAFT for preview"""
    try:
        round_number = request.form.get("round_number", type=int)
        round_deadline_str = request.form.get("round_deadline")
        
        # Parse deadline string to datetime, normalized to end-of-day (23:59:59)
        from datetime import datetime, time as dt_time
        round_deadline = None
        if round_deadline_str:
            try:
                deadline_date = datetime.strptime(round_deadline_str, "%Y-%m-%d").date()
                # Normalize to end-of-day (23:59:59)
                round_deadline = datetime.combine(deadline_date, dt_time(23, 59, 59))
            except ValueError:
                flash("Invalid deadline date format", "error")
                return redirect(url_for("admin_panel"))
        
        if not round_number or round_number < 1:
            flash("Invalid round number", "error")
            return redirect(url_for("admin_panel"))
        
        # Check for existing live matches in this round (not drafts)
        existing_live_matches = Match.query.filter_by(round=round_number, is_draft=False).first()
        if existing_live_matches:
            flash(f"Round {round_number} has already been generated and confirmed", "error")
            return redirect(url_for("admin_panel"))
        
        # Check for existing draft matches - delete them to regenerate
        existing_drafts = Match.query.filter_by(round=round_number, is_draft=True).all()
        if existing_drafts:
            for draft in existing_drafts:
                db.session.delete(draft)
            db.session.commit()
        
        # Check if settings allow generation
        settings = LeagueSettings.query.first()
        if settings and settings.current_phase == "playoff_preview":
            flash("Cannot generate Swiss rounds while in playoff phase", "error")
            return redirect(url_for("admin_panel"))
        
        # TRANSITION TO PLAYOFFS LOGIC
        if round_number > settings.swiss_rounds_count:
            # Determine playoff phase based on round number relative to swiss rounds
            # swiss_rounds_count + 1 = Quarterfinals
            # swiss_rounds_count + 2 = Semifinals
            # swiss_rounds_count + 3 = Finals
            if round_number == settings.swiss_rounds_count + 1:
                phase_type = "quarterfinal"
            elif round_number == settings.swiss_rounds_count + 2:
                phase_type = "semifinal"
            elif round_number == settings.swiss_rounds_count + 3:
                phase_type = "final"
            else:
                flash(f"Round {round_number} exceeds the scheduled league rounds.", "error")
                return redirect(url_for("admin_panel"))

            from utils import generate_playoff_bracket
            matches = generate_playoff_bracket(round_number, phase_type)
            
            if not matches:
                flash(f"Could not generate {phase_type} matches. Ensure playoffs are approved and teams are qualified.", "error")
                return redirect(url_for("admin_panel"))
        else:
            # Generate the Swiss pairings
            from utils import generate_round_pairings
            matches = generate_round_pairings(round_number)
        
        if not matches:
            flash("No matches generated - check team count", "error")
            return redirect(url_for("admin_panel"))
        
        # Mark all generated matches as DRAFT and set deadline
        for match in matches:
            match.is_draft = True
            if round_deadline:
                match.round_deadline = round_deadline
        db.session.commit()
        
        # Redirect to preview page instead of sending emails
        flash(f"📋 Round {round_number} preview generated with {len(matches)} match(es). Review and confirm below.", "info")
        return redirect(url_for("round_preview", round_number=round_number))
        
    except Exception as e:
        logging.error(f"Error generating round: {str(e)}")
        flash(f"Error generating round: {str(e)}", "error")
        return redirect(url_for("admin_panel"))


@app.route("/admin/extend-round-deadline", methods=["POST"])
@require_admin_auth
def extend_round_deadline():
    """Extend the deadline for a round"""
    try:
        round_number = request.form.get("round_number", type=int)
        new_deadline_str = request.form.get("new_deadline")
        
        if not round_number or not new_deadline_str:
            flash("Round number and new deadline are required", "error")
            return redirect(url_for("admin_panel"))
        
        from datetime import datetime, time as dt_time
        try:
            deadline_date = datetime.strptime(new_deadline_str, "%Y-%m-%d").date()
            # Normalize to end-of-day (23:59:59)
            new_deadline = datetime.combine(deadline_date, dt_time(23, 59, 59))
        except ValueError:
            flash("Invalid deadline date format", "error")
            return redirect(url_for("admin_panel"))
        
        # Update ACTIVE matches in this round (not completed/walkover) and draft matches
        matches = Match.query.filter(
            Match.round == round_number,
            db.or_(
                Match.status.notin_(['completed', 'walkover']),
                Match.is_draft == True,
                Match.status == None  # Include drafts with no status
            )
        ).all()
        if not matches:
            flash(f"No active matches found for Round {round_number}. All matches may already be completed.", "info")
            return redirect(url_for("admin_panel"))
        
        for match in matches:
            match.round_deadline = new_deadline
        db.session.commit()
        
        flash(f"Round {round_number} deadline extended to {deadline_date.strftime('%B %d, %Y')} for {len(matches)} active match(es)", "success")
        return redirect(url_for("admin_panel"))
        
    except Exception as e:
        logging.error(f"Error extending deadline: {str(e)}")
        flash(f"Error extending deadline: {str(e)}", "error")
        return redirect(url_for("admin_panel"))


@app.route("/admin/round-preview/<int:round_number>")
@require_admin_auth
def round_preview(round_number):
    """Show preview of generated round pairings before confirmation"""
    # Get draft matches for this round
    draft_matches = Match.query.filter_by(round=round_number, is_draft=True).all()
    
    if not draft_matches:
        flash(f"No preview found for Round {round_number}. Generate the round first.", "error")
        return redirect(url_for("admin_panel"))
    
    # Get all teams involved and rank them
    all_teams_set = set()
    for match in draft_matches:
        if match.team_a_id:
            all_teams_set.add(match.team_a_id)
        if match.team_b_id:
            all_teams_set.add(match.team_b_id)
    
    all_teams = [Team.query.get(tid) for tid in all_teams_set if Team.query.get(tid)]
    # Sort teams by ranking (same logic as leaderboard)
    ranked_teams = sorted(all_teams, key=lambda t: (-t.points, -t.sets_diff, -t.games_diff, -t.wins, t.team_name))
    team_rank_map = {team.id: idx + 1 for idx, team in enumerate(ranked_teams)}
    
    # Build preview data with team info and pairing reasons
    preview_data = []
    for match in draft_matches:
        team_a = Team.query.get(match.team_a_id)
        team_b = Team.query.get(match.team_b_id) if match.team_b_id else None
        
        # Create a simple, meaningful reason
        if team_b is None:
            pairing_reason = "Bye week (automatic win)"
        else:
            pairing_reason = "Matched by Swiss pairing algorithm"
        
        preview_data.append({
            'match': match,
            'team_a': team_a,
            'team_b': team_b,
            'team_a_rank': team_rank_map.get(match.team_a_id, 0) if team_a else 0,
            'is_bye': team_b is None,
            'reason': pairing_reason
        })
    
    # Sort pairings by team_a rank (highest rank first)
    preview_data.sort(key=lambda x: x['team_a_rank'])
    
    return render_template(
        "round-preview.html",
        round_number=round_number,
        preview_data=preview_data,
        match_count=len(draft_matches),
        ranked_teams=ranked_teams
    )


@app.route("/admin/confirm-round/<int:round_number>", methods=["POST"])
@require_admin_auth
def confirm_round(round_number):
    """Confirm round preview - make matches live and send emails"""
    try:
        # Get draft matches for this round
        draft_matches = Match.query.filter_by(round=round_number, is_draft=True).all()
        
        if not draft_matches:
            flash(f"No preview found for Round {round_number}", "error")
            return redirect(url_for("admin_panel"))
        
        # Promote drafts to live matches
        for match in draft_matches:
            match.is_draft = False
        db.session.commit()
        
        # Send email notifications to teams
        from utils import send_email_notification
        teams_to_notify = set()
        for match in draft_matches:
            if match.team_a_id:
                teams_to_notify.add(match.team_a_id)
            if match.team_b_id:
                teams_to_notify.add(match.team_b_id)
        
        for team_id in teams_to_notify:
            team = Team.query.get(team_id)
            if team and (team.player1_email or team.player2_email):
                # Find the opponent in matches
                team_matches = [m for m in draft_matches if m.team_a_id == team_id or m.team_b_id == team_id]
                
                match_details = ""
                for match in team_matches:
                    opponent_id = match.team_b_id if match.team_a_id == team_id else match.team_a_id
                    if opponent_id:
                        opponent = Team.query.get(opponent_id)
                        match_details += f"vs {opponent.team_name}\n"
                    else:
                        match_details += "BYE (automatic win)\n"
                
                # Get base URL for link
                base_url = os.environ.get('APP_BASE_URL', 'https://goeclectic.xyz')
                matches_link = f"{base_url}/my-matches/{team.access_token}"
                
                # Get deadline from any match in this round (all matches share same deadline)
                deadline_text = "Sunday 23:59"  # Default
                if team_matches and team_matches[0].round_deadline:
                    deadline_text = team_matches[0].round_deadline.strftime('%A, %B %d at %H:%M')
                
                email_body = f"""Hello {team.team_name},

Round {round_number} has been generated! Here are your matchups:

{match_details}
Deadline: Submit your match result by {deadline_text}

📍 View and manage your matches here: {matches_link}

Best of luck!

BD Padel League Admin"""
                # Send to player 1
                if team.player1_email:
                    send_email_notification(
                        team.player1_email,
                        f"Round {round_number} Generated - Your Matchups",
                        email_body
                    )
                
                # Send to player 2 if different from player 1
                if team.player2_email and team.player2_email != team.player1_email:
                    send_email_notification(
                        team.player2_email,
                        f"Round {round_number} Generated - Your Matchups",
                        email_body
                    )
        
        flash(f"✅ Round {round_number} confirmed with {len(draft_matches)} match(es)! Emails sent to all teams.", "success")
        return redirect(url_for("admin_panel"))
        
    except Exception as e:
        logging.error(f"Error confirming round: {str(e)}")
        flash(f"Error confirming round: {str(e)}", "error")
        return redirect(url_for("admin_panel"))


@app.route("/admin/discard-round/<int:round_number>", methods=["POST"])
@require_admin_auth
def discard_round(round_number):
    """Discard draft round preview - delete all draft matches"""
    try:
        # Get draft matches for this round
        draft_matches = Match.query.filter_by(round=round_number, is_draft=True).all()
        
        if not draft_matches:
            flash(f"No preview found for Round {round_number}", "error")
            return redirect(url_for("admin_panel"))
        
        # Delete all draft matches
        for match in draft_matches:
            db.session.delete(match)
        db.session.commit()
        
        flash(f"🗑️ Round {round_number} preview discarded. You can regenerate when ready.", "info")
        return redirect(url_for("admin_panel"))
        
    except Exception as e:
        logging.error(f"Error discarding round: {str(e)}")
        flash(f"Error discarding round: {str(e)}", "error")
        return redirect(url_for("admin_panel"))


@app.route("/admin/reset-match-booking/<int:match_id>", methods=["POST"])
@require_admin_auth
def reset_match_booking(match_id):
    """Reset a match's booking details so teams need to reschedule"""
    match = Match.query.get_or_404(match_id)

    # Clear booking details
    match.booking_details = None
    match.booking_confirmed = False
    match.match_datetime = None
    match.match_date = None
    match.court = None

    db.session.commit()

    # Get team names for flash message
    team_a = Team.query.get(match.team_a_id)
    team_b = Team.query.get(match.team_b_id)
    team_a_name = team_a.team_name if team_a else "Team A"
    team_b_name = team_b.team_name if team_b else "Team B"

    flash(f"✅ Match booking reset for {team_a_name} vs {team_b_name}. Teams will need to reschedule.", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/reset-round-status/<int:round_number>", methods=["POST"])
@require_admin_auth
def reset_round_status(round_number):
    """Reset all matches in a round back to scheduled status (useful for future rounds)"""
    matches = Match.query.filter_by(round=round_number).all()

    if not matches:
        flash(f"No matches found for Round {round_number}", "error")
        return redirect(url_for("admin_panel"))

    reset_count = 0
    for match in matches:
        if match.status == "completed":
            # Reverse stats if already calculated
            if match.stats_calculated:
                team_a = Team.query.get(match.team_a_id)
                team_b = Team.query.get(match.team_b_id)

                if team_a and team_b:
                    # Reverse team stats
                    team_a.sets_for -= match.sets_a
                    team_a.sets_against -= match.sets_b
                    team_a.games_for -= match.games_a
                    team_a.games_against -= match.games_b

                    team_b.sets_for -= match.sets_b
                    team_b.sets_against -= match.sets_a
                    team_b.games_for -= match.games_b
                    team_b.games_against -= match.games_a

                    # Reverse wins/losses/draws
                    if match.winner_id == team_a.id:
                        team_a.wins -= 1
                        team_a.points -= 3
                        team_b.losses -= 1
                    elif match.winner_id == team_b.id:
                        team_b.wins -= 1
                        team_b.points -= 3
                        team_a.losses -= 1
                    elif match.winner_id is None:
                        team_a.draws -= 1
                        team_a.points -= 1
                        team_b.draws -= 1
                        team_b.points -= 1

            # Reset match to scheduled
            match.status = "scheduled"
            match.score_a = None
            match.score_b = None
            match.sets_a = 0
            match.sets_b = 0
            match.games_a = 0
            match.games_b = 0
            match.winner_id = None
            match.verified = False
            match.stats_calculated = False
            match.score_submission_a = None
            match.score_submission_b = None
            match.score_submitted_by_a = False
            match.score_submitted_by_b = False

            reset_count += 1

    db.session.commit()
    flash(f"✅ Reset {reset_count} match(es) in Round {round_number} back to scheduled status. All stats reversed.", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/reschedules")
@require_admin_auth
def reschedule_dashboard():
    """Admin dashboard for managing reschedule requests"""
    pending_reschedules = get_pending_reschedules()
    max_allowed = get_max_reschedules_per_round()

    # Get all reschedules with match and team details
    reschedule_details = []
    for reschedule in pending_reschedules:
        match = Match.query.get(reschedule.match_id) if reschedule.match_id else None
        requester_team = Team.query.get(reschedule.requester_team_id)
        opponent_team = None

        if match and requester_team:
            opponent_id = match.team_b_id if match.team_a_id == requester_team.id else match.team_a_id
            opponent_team = Team.query.get(opponent_id)

        reschedule_details.append({
            'reschedule': reschedule,
            'match': match,
            'requester_team': requester_team,
            'opponent_team': opponent_team
        })

    return render_template(
        "reschedule_dashboard.html",
        reschedule_details=reschedule_details,
        max_allowed=max_allowed,
        total_pending=len(reschedule_details)
    )

@app.route("/admin/approve-reschedule/<int:reschedule_id>", methods=["POST"])
@require_admin_auth
def approve_reschedule(reschedule_id):
    """Approve a reschedule request"""
    reschedule = Reschedule.query.get_or_404(reschedule_id)

    if reschedule.status != "pending":
        flash("Reschedule request is not pending", "error")
        return redirect(url_for("reschedule_dashboard"))

    try:
        from datetime import datetime

        # Update match with new date/time
        match = Match.query.get(reschedule.match_id) if reschedule.match_id else None
        if match:
            # Parse the proposed time
            proposed_time = reschedule.proposed_time
            if " at " in proposed_time:
                date_str, time_str = proposed_time.split(" at ")
                
                # Convert date format from "2025-11-25" to "Tuesday, November 25"
                parsed_date = datetime.strptime(date_str, "%Y-%m-%d")
                formatted_date = parsed_date.strftime("%A, %B %d")
                
                # Convert time format from "18:30" to "06:30 PM"
                time_obj = datetime.strptime(time_str, "%H:%M")
                formatted_time = time_obj.strftime("%I:%M %p")
                
                # Create fully formatted datetime string for booking details
                booking_datetime_str = f"{formatted_date} at {formatted_time}"
                
                # Set all booking-related fields to match normal booking confirmation
                # Keep match_date in original format (YYYY-MM-DD), only update match_datetime
                if not match.match_date:
                    match.match_date = date_str  # Set to YYYY-MM-DD format if empty
                match.match_datetime = parsed_date.replace(hour=time_obj.hour, minute=time_obj.minute)
                match.court = "Court assigned on arrival"
                match.booking_details = f"{booking_datetime_str}\nCourt assigned on arrival\n✓ Confirmed by both teams"
                match.booking_confirmed = True  # Admin approval counts as booking confirmation

            # Update reschedule status
            reschedule.status = "approved"
            reschedule.approved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Increment team's reschedule usage
            requester_team = Team.query.get(reschedule.requester_team_id)
            if requester_team:
                requester_team.reschedules_used += 1

            db.session.commit()

            # Send approval notifications
            from utils import send_email_notification
            opponent_id = match.team_b_id if match.team_a_id == requester_team.id else match.team_a_id
            opponent = Team.query.get(opponent_id)

            approval_body = f"""Hi {requester_team.team_name},

✅ Your reschedule request has been APPROVED by admin.

Match Details:
- Round: {match.round}
- Opponent: {opponent.team_name if opponent else 'Unknown'}
- New Time: {reschedule.proposed_time}
- DEADLINE: Wednesday 23:59 (absolute deadline for makeup matches)

⚠️ IMPORTANT: This is now a MAKEUP MATCH. You must complete it by Wednesday 23:59 or automatic walkover will be awarded to your opponent.

Team Reschedules Used: {requester_team.reschedules_used}/2

- BD Padel League
"""
            # Notify requester team
            if requester_team.player1_email:
                send_email_notification(requester_team.player1_email, f"Reschedule APPROVED - Round {match.round}", approval_body)
            if requester_team.player2_email:
                send_email_notification(requester_team.player2_email, f"Reschedule APPROVED - Round {match.round}", approval_body)

            # Notify opponent team
            if opponent:
                opponent_approval_body = f"""Hi {opponent.team_name},

The reschedule request from {requester_team.team_name} has been APPROVED by admin.

Match Details:
- Round: {match.round}
- Opponent: {requester_team.team_name}
- New Time: {reschedule.proposed_time}
- DEADLINE: Wednesday 23:59 (absolute deadline for makeup matches)

⚠️ IMPORTANT: This is now a MAKEUP MATCH. You must complete it by Wednesday 23:59 or automatic walkover will be awarded to {requester_team.team_name}.

- BD Padel League
"""
                if opponent.player1_email:
                    send_email_notification(opponent.player1_email, f"Reschedule APPROVED - Round {match.round}", opponent_approval_body)
                if opponent.player2_email:
                    send_email_notification(opponent.player2_email, f"Reschedule APPROVED - Round {match.round}", opponent_approval_body)

            flash(f"Reschedule approved for {requester_team.team_name if requester_team else 'Unknown team'}", "success")
        else:
            flash("Associated match not found", "error")

    except Exception as e:
        db.session.rollback()
        flash(f"Error approving reschedule: {str(e)}", "error")

    return redirect(url_for("reschedule_dashboard"))

@app.route("/admin/reject-reschedule/<int:reschedule_id>", methods=["POST"])
@require_admin_auth
def reject_reschedule(reschedule_id):
    """Reject a reschedule request"""
    reschedule = Reschedule.query.get_or_404(reschedule_id)

    if reschedule.status != "pending":
        flash("Reschedule request is not pending", "error")
        return redirect(url_for("reschedule_dashboard"))

    try:
        from datetime import datetime

        # Update reschedule status
        reschedule.status = "rejected"
        reschedule.rejected_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        db.session.commit()

        # Send rejection notifications
        from utils import send_email_notification
        requester_team = Team.query.get(reschedule.requester_team_id)
        match = Match.query.get(reschedule.match_id) if reschedule.match_id else None

        if requester_team and match:
            opponent_id = match.team_b_id if match.team_a_id == requester_team.id else match.team_a_id
            opponent = Team.query.get(opponent_id)

            rejection_body = f"""Hi {requester_team.team_name},

❌ Your reschedule request has been REJECTED by admin.

Match Details:
- Round: {match.round}
- Opponent: {opponent.team_name if opponent else 'Unknown'}
- Requested Time: {reschedule.proposed_time}

Your match remains scheduled for the original round deadline (Sunday 23:59).

If you need assistance, please contact the admin.

Team Reschedules Used: {requester_team.reschedules_used}/2

- BD Padel League
"""
            if requester_team.player1_email:
                send_email_notification(requester_team.player1_email, f"Reschedule REJECTED - Round {match.round}", rejection_body)
            if requester_team.player2_email:
                send_email_notification(requester_team.player2_email, f"Reschedule REJECTED - Round {match.round}", rejection_body)

            # Notify opponent team
            if opponent:
                opponent_rejection_body = f"""Hi {opponent.team_name},

The reschedule request from {requester_team.team_name} has been REJECTED by admin.

Match Details:
- Round: {match.round}
- Original Deadline: Sunday 23:59

Your match remains scheduled for the original deadline.

- BD Padel League
"""
                if opponent.player1_email:
                    send_email_notification(opponent.player1_email, f"Reschedule REJECTED - Round {match.round}", opponent_rejection_body)
                if opponent.player2_email:
                    send_email_notification(opponent.player2_email, f"Reschedule REJECTED - Round {match.round}", opponent_rejection_body)

        flash(f"Reschedule rejected for {requester_team.team_name if requester_team else 'Unknown team'}", "success")

    except Exception as e:
        db.session.rollback()
        flash(f"Error rejecting reschedule: {str(e)}", "error")

    return redirect(url_for("reschedule_dashboard"))

@app.route("/admin/check-deadlines", methods=["POST"])
@require_admin_auth
def check_deadlines():
    """Manually check for deadline violations and apply walkovers"""
    walkovers = check_deadline_violations()

    total_walkovers = len(walkovers['regular']) + len(walkovers['makeup'])

    if walkovers['regular']:
        for walkover in walkovers['regular']:
            flash(f"⚠️ Regular Match Walkover: {walkover['team_a']} vs {walkover['team_b']} - Round {walkover['round']} (missed {walkover['deadline']} deadline)", "warning")

    if walkovers['makeup']:
        for walkover in walkovers['makeup']:
            flash(f"⚠️ Makeup Match Walkover: {walkover['opponent_team']} wins vs {walkover['requester_team']} (missed {walkover['deadline']} deadline)", "warning")

    if total_walkovers > 0:
        flash(f"✅ Processed {total_walkovers} deadline violation(s) with automatic walkovers.", "success")
    else:
        flash("✅ No deadline violations found. All matches are within their deadlines.", "success")

    return redirect(url_for("reschedule_dashboard"))

@app.route("/admin/resend-round-emails/<int:round_number>", methods=["POST"])
@require_admin_auth
def resend_round_emails(round_number):
    """Manually resend email notifications for a specific round"""
    from utils import send_email_notification

    # Get all matches for this round
    matches = Match.query.filter_by(round=round_number).all()

    if not matches:
        flash(f"No matches found for Round {round_number}", "error")
        return redirect(url_for("admin_panel"))

    round_dates = get_round_date_range(round_number)
    base_url = "https://goeclectic.xyz"

    emails_sent = 0
    emails_failed = 0

    for match in matches:
        try:
            if match.status == "bye":
                # Handle bye notification
                bye_team = Team.query.get(match.team_a_id)
                if bye_team:
                    bye_body = f"""Hi {bye_team.team_name},

Round {round_number} has been generated!

🏖️ You have a BYE this round - no match to play.

Round Dates: {round_dates}

You'll automatically advance to the next round. Enjoy your break!

- BD Padel League
"""
                    if bye_team.player1_email:
                        if send_email_notification(bye_team.player1_email, f"Round {round_number} - BYE Week", bye_body):
                            emails_sent += 1
                        else:
                            emails_failed += 1
                    if bye_team.player2_email:
                        if send_email_notification(bye_team.player2_email, f"Round {round_number} - BYE Week", bye_body):
                            emails_sent += 1
                        else:
                            emails_failed += 1
            else:
                # Handle regular match notifications
                team_a = Team.query.get(match.team_a_id)
                team_b = Team.query.get(match.team_b_id)

                if team_a and team_b:
                    # Access link for each team
                    base_url = "https://goeclectic.xyz"

                    # Team A notification
                    team_a_link = f"{base_url}/my-matches/{team_a.access_token}"
                    team_a_body = f"""Hi {team_a.team_name},

Round {round_number} has been generated!

🎾 Your Match:
- Opponent: {team_b.team_name}
- Round Dates: {round_dates}
- Deadline: Sunday 23:59

📋 Next Steps:
1. Coordinate with your opponent to book a court
2. Play your match before Sunday 23:59
3. Submit scores immediately after the match

🔗 Your Match Page: {team_a_link}

Opponent Contact:
- {team_b.player1_name}: {team_b.player1_email or team_b.player1_phone}
- {team_b.player2_name}: {team_b.player2_email or team_b.player2_phone}

Good luck! 🎾

- BD Padel League
"""
                    if team_a.player1_email:
                        if send_email_notification(team_a.player1_email, f"Round {round_number} Pairing - vs {team_b.team_name}", team_a_body):
                            emails_sent += 1
                        else:
                            emails_failed += 1
                    if team_a.player2_email:
                        if send_email_notification(team_a.player2_email, f"Round {round_number} Pairing - vs {team_b.team_name}", team_a_body):
                            emails_sent += 1
                        else:
                            emails_failed += 1

                    # Team B notification
                    team_b_link = f"{base_url}/my-matches/{team_b.access_token}"
                    team_b_body = f"""Hi {team_b.team_name},

Round {round_number} has been generated!

🎾 Your Match:
- Opponent: {team_a.team_name}
- Round Dates: {round_dates}
- Deadline: Sunday 23:59

📋 Next Steps:
1. Coordinate with your opponent to book a court
2. Play your match before Sunday 23:59
3. Submit scores immediately after the match

🔗 Your Match Page: {team_b_link}

Opponent Contact:
- {team_a.player1_name}: {team_a.player1_email or team_a.player1_phone}
- {team_a.player2_name}: {team_a.player2_email or team_a.player2_phone}

Good luck! 🎾

- BD Padel League
"""
                    if team_b.player1_email:
                        if send_email_notification(team_b.player1_email, f"Round {round_number} Pairing - vs {team_a.team_name}", team_b_body):
                            emails_sent += 1
                        else:
                            emails_failed += 1
                    if team_b.player2_email:
                        if send_email_notification(team_b.player2_email, f"Round {round_number} Pairing - vs {team_a.team_name}", team_b_body):
                            emails_sent += 1
                        else:
                            emails_failed += 1

        except Exception as e:
            print(f"[EMAIL ERROR] Failed to send emails for match {match.id}: {e}")
            emails_failed += 1

    if emails_sent > 0:
        flash(f"✅ Successfully sent {emails_sent} email(s) for Round {round_number}", "success")
    if emails_failed > 0:
        flash(f"⚠️ Failed to send {emails_failed} email(s). Check SMTP configuration.", "warning")

    return redirect(url_for("admin_panel"))

@app.route("/admin/update-match/<int:match_id>", methods=["POST"])
@require_admin_auth
def update_match(match_id):
    match = Match.query.get(match_id)
    if not match:
        flash("Match not found", "error")
        return redirect(url_for("admin_panel"))

    # Get form data
    score_a_str = request.form.get("score_a", "").strip()
    score_b_str = request.form.get("score_b", "").strip()
    match_date = request.form.get("match_date", "").strip()
    court = request.form.get("court", "").strip()

    # If this is a bye round, don't process scores
    if match.status == "bye":
        flash("Cannot update bye round scores", "error")
        return redirect(url_for("admin_panel"))

    # Check if we have scores to process
    if not score_a_str or not score_b_str:
        flash("Please enter scores for both teams", "error")
        return redirect(url_for("admin_panel"))

    # CRITICAL: If stats were already calculated, reverse them first
    if match.stats_calculated:
        team_a = Team.query.get(match.team_a_id)
        team_b = Team.query.get(match.team_b_id)

        if team_a and team_b:
            # Reverse team stats
            team_a.sets_for -= match.sets_a
            team_a.sets_against -= match.sets_b
            team_a.games_for -= match.games_a
            team_a.games_against -= match.games_b

            team_b.sets_for -= match.sets_b
            team_b.sets_against -= match.sets_a
            team_b.games_for -= match.games_b
            team_b.games_against -= match.games_a

            # Reverse wins/losses/draws
            if match.winner_id == team_a.id:
                team_a.wins -= 1
                team_a.points -= 3
                team_b.losses -= 1
            elif match.winner_id == team_b.id:
                team_b.wins -= 1
                team_b.points -= 3
                team_a.losses -= 1
            elif match.winner_id is None and match.status == "completed":
                team_a.draws -= 1
                team_a.points -= 1
                team_b.draws -= 1
                team_b.points -= 1

    # Calculate new match result
    sets_a, sets_b, games_a, games_b, winner = calculate_match_result(score_a_str, score_b_str)

    if winner is None:
        flash("Invalid score format. Use format like '6-4, 6-3' or '6-4, 3-6, 10-8'", "error")
        return redirect(url_for("admin_panel"))

    # Update match record
    match.score_a = score_a_str
    match.score_b = score_b_str
    match.sets_a = sets_a
    match.sets_b = sets_b
    match.games_a = games_a
    match.games_b = games_b
    match.match_date = match_date
    match.court = court
    match.status = "completed"
    match.stats_calculated = True

    # Update team stats
    team_a = Team.query.get(match.team_a_id)
    team_b = Team.query.get(match.team_b_id)

    if team_a and team_b:
        # Add sets and games
        team_a.sets_for += sets_a
        team_a.sets_against += sets_b
        team_a.games_for += games_a
        team_a.games_against += games_b

        team_b.sets_for += sets_b
        team_b.sets_against += sets_a
        team_b.games_for += games_b
        team_b.games_against += games_a

        # Update wins/losses/draws and points (3 for win, 1 for draw, 0 for loss)
        if winner == 'a':
            team_a.wins += 1
            team_a.points += 3
            team_b.losses += 1
            match.winner_id = team_a.id
        elif winner == 'b':
            team_b.wins += 1
            team_b.points += 3
            team_a.losses += 1
            match.winner_id = team_b.id
        elif winner == 'draw':
            team_a.draws += 1
            team_a.points += 1
            team_b.draws += 1
            team_b.points += 1
            match.winner_id = None

    db.session.commit()
    flash(f"Match scores updated successfully for {match.team_a.team_name} vs {match.team_b.team_name}", "success")
    return redirect(url_for("admin_panel"))

@app.route("/admin/confirm-team/<int:team_id>", methods=["POST"])
@require_admin_auth
def confirm_team(team_id):
    team = Team.query.get(team_id)
    if team:
        team.confirmed = not team.confirmed
        # When admin confirms, also mark Player 2 as confirmed (admin override)
        if team.confirmed:
            team.player2_confirmed = True
        else:
            team.player2_confirmed = False
        db.session.commit()
        status = "confirmed" if team.confirmed else "unconfirmed"
        flash(f"Team {team.team_name} {status}!", "success")
    else:
        flash("Team not found", "error")
    return redirect(url_for("admin_panel"))

@app.route("/admin/toggle-team-status/<int:team_id>", methods=["POST"])
@require_admin_auth
def toggle_team_status(team_id):
    """Toggle team between active and inactive status for league"""
    team = Team.query.get(team_id)
    if team:
        new_status = 'inactive' if team.status == 'active' else 'active'
        team.status = new_status
        db.session.commit()
        flash(f"Team {team.team_name} is now {new_status}!", "success")
    else:
        flash("Team not found", "error")
    return redirect(url_for("admin_panel"))

@app.route("/admin/edit-team/<int:team_id>", methods=["GET", "POST"])
@require_admin_auth
def edit_team(team_id):
    team = Team.query.get(team_id)
    if not team:
        flash("Team not found", "error")
        return redirect(url_for("admin_panel"))

    # Store original phone numbers to check for changes
    old_player1_phone = team.player1_phone
    old_player2_phone = team.player2_phone

    if request.method == "POST":
        team_name = request.form.get("team_name", "").strip()
        player1_name = request.form.get("player1_name", "").strip()
        player1_email = request.form.get("player1_email", "").strip()
        player1_phone = request.form.get("player1_phone", "").strip()
        player2_name = request.form.get("player2_name", "").strip()
        player2_email = request.form.get("player2_email", "").strip()
        player2_phone = request.form.get("player2_phone", "").strip()

        errors = []

        if not team_name:
            errors.append("Team name is required")

        if not player1_name:
            errors.append("Player 1 name is required")

        if not player2_name:
            errors.append("Player 2 name is required")

        if not player1_phone:
            errors.append("Player 1 phone is required")

        if not player2_phone:
            errors.append("Player 2 phone is required")

        normalized_phone1 = normalize_phone_number(player1_phone) if player1_phone else None
        normalized_phone2 = normalize_phone_number(player2_phone) if player2_phone else None

        if player1_phone and not normalized_phone1:
            errors.append("Player 1 phone number is invalid")

        if player2_phone and not normalized_phone2:
            errors.append("Player 2 phone number is invalid")

        if player1_email and not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', player1_email):
            errors.append("Player 1 email format is invalid")

        if player2_email and not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', player2_email):
            errors.append("Player 2 email format is invalid")

        if errors:
            for error in errors:
                flash(error, "error")
            return render_template("admin_edit_team.html", team=team)

        team.team_name = team_name
        team.team_name_canonical = normalize_team_name(team_name)
        team.player1_name = player1_name
        team.player1_email = player1_email if player1_email else None
        team.player1_phone = normalized_phone1
        team.player2_name = player2_name
        team.player2_email = player2_email if player2_email else None
        team.player2_phone = normalized_phone2

        # Update associated Player records if phone number changed
        if old_player1_phone != normalized_phone1:
            player1 = Player.query.filter_by(phone=old_player1_phone).first()
            if player1:
                player1.phone = normalized_phone1
                player1.name = player1_name
                player1.email = player1_email if player1_email else None

        if old_player2_phone != normalized_phone2:
            player2 = Player.query.filter_by(phone=old_player2_phone).first()
            if player2:
                player2.phone = normalized_phone2
                player2.name = player2_name
                player2.email = player2_email if player2_email else None

        try:
            db.session.commit()
            flash(f"Team {team_name} updated successfully!", "success")
            return redirect(url_for("admin_panel"))
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating team: {str(e)}", "error")
            return render_template("admin_edit_team.html", team=team)

    return render_template("admin_edit_team.html", team=team)

@app.route("/admin/delete-team/<int:team_id>", methods=["POST"])
@require_admin_auth
def delete_team(team_id):
    team = Team.query.get(team_id)
    if not team:
        flash("Team not found", "error")
        return redirect(url_for("admin_panel"))
    # Optionally: delete that team's matches as well
    # For safety, only allow delete if team has no completed matches
    has_matches = Match.query.filter(
        (Match.team_a_id == team_id) | (Match.team_b_id == team_id)
    ).count() > 0
    if has_matches:
        flash("Cannot delete team with scheduled or recorded matches. Remove matches first.", "error")
        return redirect(url_for("admin_panel"))
    db.session.delete(team)
    db.session.commit()
    flash("Team deleted.", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/deny-reschedule/<int:reschedule_id>", methods=["POST"])
@require_admin_auth
def deny_reschedule(reschedule_id):
    reschedule = Reschedule.query.get_or_404(reschedule_id)
    reschedule.status = "denied"
    db.session.commit()
    flash(f"Reschedule request denied for Match {reschedule.match_id}")
    return redirect(url_for("admin_panel"))

@app.route("/admin/approve-substitute/<int:substitute_id>", methods=["POST"])
@require_admin_auth
def approve_substitute(substitute_id):
    substitute = Substitute.query.get_or_404(substitute_id)
    substitute.status = "approved"

    # Increment substitute counter for the team
    team = Team.query.get(substitute.team_id)
    match = Match.query.get(substitute.match_id)

    if team:
        team.subs_used += 1

    # Create a Player record for the substitute so they can accumulate stats
    from datetime import datetime
    if substitute.phone:
        substitute_player = Player.query.filter_by(phone=substitute.phone).first()
        if not substitute_player:
            substitute_player = Player(
                name=substitute.name,
                phone=substitute.phone,
                email=substitute.email,
                current_team_id=team.id if team else None,
                created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
            db.session.add(substitute_player)
            db.session.flush()
        
        # Link the player to the substitute record
        substitute.player_id = substitute_player.id

    db.session.commit()

    # Send confirmation emails to all parties
    from utils import send_email_notification

    if match and team:
        # Get replaced player's name
        replaced_player_name = team.player1_name if substitute.replaces_player_number == 1 else team.player2_name

        # Get opponent team
        opponent_id = match.team_b_id if match.team_a_id == team.id else match.team_a_id
        opponent_team = Team.query.get(opponent_id)

        subject = f"Substitute Request APPROVED - Round {match.round}"

        # Email to Player 1
        if team.player1_email:
            body1 = f"""Hello {team.player1_name},

✅ GOOD NEWS! Your substitute request has been APPROVED by the admin.

Match Details:
- Round: {match.round}
- Team: {team.team_name}
- Substitute: {substitute.name} ({substitute.email})
- Replacing: {replaced_player_name}
- Match ID: {match.id}

Your substitute is now officially approved for this match. Please coordinate with {substitute.name} for the match schedule.

Team Substitute Usage: {team.subs_used}/2

Thank you!
Padel League Hub"""
            send_email_notification(team.player1_email, subject, body1)

        # Email to Player 2
        if team.player2_email:
            body2 = f"""Hello {team.player2_name},

✅ GOOD NEWS! Your team's substitute request has been APPROVED by the admin.

Match Details:
- Round: {match.round}
- Team: {team.team_name}
- Substitute: {substitute.name} ({substitute.email})
- Replacing: {replaced_player_name}
- Match ID: {match.id}

Your substitute is now officially approved for this match. Please coordinate with {substitute.name} for the match schedule.

Team Substitute Usage: {team.subs_used}/2

Thank you!
Padel League Hub"""
            send_email_notification(team.player2_email, subject, body2)

        # Email to Substitute
        if substitute.email:
            sub_body = f"""Hello {substitute.name},

✅ CONGRATULATIONS! Your substitute request has been APPROVED by the admin.

Match Details:
- Round: {match.round}
- Team: {team.team_name}
- Team Players: {team.player1_name} & {team.player2_name}
- You will replace: {replaced_player_name}
- Match ID: {match.id}

You are now officially approved to play as a substitute for this match. Please coordinate with the team for the match schedule and details.

Thank you for participating!
Padel League Hub"""
            send_email_notification(substitute.email, subject, sub_body)

        # Email to OPPONENT TEAM
        if opponent_team:
            opponent_subject = f"Opponent Using Substitute - Round {match.round}"
            opponent_body = f"""Hello {opponent_team.team_name},

📢 FYI: Your opponent will be using a substitute player for your upcoming match.

Match Details:
- Round: {match.round}
- Opponent Team: {team.team_name}
- Substitute Player: {substitute.name}
- Replacing: {replaced_player_name}

The substitute has been approved by the admin. Please proceed with the match as scheduled.

Good luck!
Padel League Hub"""

            if opponent_team.player1_email:
                send_email_notification(opponent_team.player1_email, opponent_subject, opponent_body)
            if opponent_team.player2_email:
                send_email_notification(opponent_team.player2_email, opponent_subject, opponent_body)

    flash(f"Substitute request approved for Match {substitute.match_id}. Team now has {team.subs_used}/2 substitutes used. Confirmation emails sent to all parties.", "success")
    return redirect(url_for("admin_panel"))

@app.route("/admin/deny-substitute/<int:substitute_id>", methods=["POST"])
@require_admin_auth
def deny_substitute(substitute_id):
    substitute = Substitute.query.get_or_404(substitute_id)
    substitute.status = "denied"

    team = Team.query.get(substitute.team_id)
    match = Match.query.get(substitute.match_id)

    db.session.commit()

    # Send notification emails
    from utils import send_email_notification

    if match and team:
        subject = f"Substitute Request DENIED - Round {match.round}"

        # Email to Player 1
        if team.player1_email:
            body1 = f"""Hello {team.player1_name},

Your substitute request has been DENIED by the admin.

Match Details:
- Round: {match.round}
- Team: {team.team_name}
- Substitute: {substitute.name} ({substitute.email})
- Match ID: {match.id}

Please contact the admin if you have questions or to submit a different substitute request.

Team Substitute Usage: {team.subs_used}/2

Thank you!
Padel League Hub"""
            send_email_notification(team.player1_email, subject, body1)

        # Email to Player 2
        if team.player2_email:
            body2 = f"""Hello {team.player2_name},

Your team's substitute request has been DENIED by the admin.

Match Details:
- Round: {match.round}
- Team: {team.team_name}
- Substitute: {substitute.name} ({substitute.email})
- Match ID: {match.id}

Please contact the admin if you have questions or your teammate needs to submit a different substitute request.

Team Substitute Usage: {team.subs_used}/2

Thank you!
Padel League Hub"""
            send_email_notification(team.player2_email, subject, body2)

        # Email to Substitute
        if substitute.email:
            sub_body = f"""Hello {substitute.name},

Unfortunately, your substitute request has been DENIED by the admin.

Match Details:
- Round: {match.round}
- Team: {team.team_name}
- Team Players: {team.player1_name} & {team.player2_name}
- Match ID: {match.id}

You will not be playing as a substitute for this match. Please contact the team or admin if you have questions.

Thank you!
Padel League Hub"""
            send_email_notification(substitute.email, subject, sub_body)

    flash(f"Substitute request denied for Match {substitute.match_id}. Notification emails sent to all parties.")
    return redirect(url_for("admin_panel"))

@app.route("/admin/set-booking-date/<int:match_id>", methods=["POST"])
@require_admin_auth
def set_booking_date(match_id):
    """Admin sets match booking date (no restrictions). Notifies both teams via email."""
    from utils import send_email_notification
    
    match = Match.query.get_or_404(match_id)
    booking_date = request.form.get("booking_date", "").strip()
    booking_time = request.form.get("booking_time", "").strip()
    
    if not booking_date or not booking_time:
        flash("Both date and time are required.", "error")
        return redirect(url_for("admin_panel"))
    
    # Format as "YYYY-MM-DD at HH:MM"
    booking_date_formatted = f"{booking_date} at {booking_time}"
    
    # Get both teams
    team_a = Team.query.get(match.team_a_id)
    team_b = Team.query.get(match.team_b_id)
    
    if not team_a or not team_b:
        flash("Teams not found.", "error")
        return redirect(url_for("admin_panel"))
    
    # Store the admin-set booking date
    match.booking_date_admin = booking_date_formatted
    db.session.commit()
    
    # Send email notification to both teams
    subject = f"Match Booking Date Set - {team_a.team_name} vs {team_b.team_name}"
    
    # Email to Team A
    body_a = f"""Hello {team_a.player1_name},

Your match booking date has been set by the admin!

Match Details:
- Team A: {team_a.team_name}
- Team B: {team_b.team_name}
- Round: {match.round}
- Booking Date: {booking_date_formatted}

Please confirm your availability and prepare for the match.

Thank you!
Padel League Hub"""
    
    if team_a.player1_email:
        send_email_notification(team_a.player1_email, subject, body_a)
    if team_a.player2_email and team_a.player2_email != team_a.player1_email:
        send_email_notification(team_a.player2_email, subject, body_a)
    
    # Email to Team B
    body_b = f"""Hello {team_b.player1_name},

Your match booking date has been set by the admin!

Match Details:
- Team A: {team_a.team_name}
- Team B: {team_b.team_name}
- Round: {match.round}
- Booking Date: {booking_date_formatted}

Please confirm your availability and prepare for the match.

Thank you!
Padel League Hub"""
    
    if team_b.player1_email:
        send_email_notification(team_b.player1_email, subject, body_b)
    if team_b.player2_email and team_b.player2_email != team_b.player1_email:
        send_email_notification(team_b.player2_email, subject, body_b)
    
    flash(f"Booking date set to '{booking_date_formatted}'. Notification emails sent to both teams.", "success")
    return redirect(url_for("admin_panel"))

@app.route("/admin/override-match/<int:match_id>", methods=["POST"])
@require_admin_auth
def override_match(match_id):
    match = Match.query.get_or_404(match_id)
    action = request.form.get("override_action")  # completed | walkover_a | walkover_b | void
    score_a_str = request.form.get("override_score_a", "").strip()
    score_b_str = request.form.get("override_score_b", "").strip()
    note = request.form.get("override_note", "").strip()

    # Reverse prior stats if needed
    try:
        if match.stats_calculated:
            team_a = Team.query.get(match.team_a_id)
            team_b = Team.query.get(match.team_b_id)
            if team_a and team_b:
                team_a.sets_for -= match.sets_a
                team_a.sets_against -= match.sets_b
                team_a.games_for -= match.games_a
                team_a.games_against -= match.games_b
                team_b.sets_for -= match.sets_b
                team_b.sets_against -= match.sets_a
                team_b.games_for -= match.games_b
                team_b.games_against -= match.games_a
                if match.winner_id == team_a.id:
                    team_a.wins -= 1
                    team_a.points -= 3
                    team_b.losses -= 1
                elif match.winner_id == team_b.id:
                    team_b.wins -= 1
                    team_b.points -= 3
                    team_a.losses -= 1
                elif match.winner_id is None and match.status == "completed":
                    team_a.draws -= 1
                    team_a.points -= 1
                    team_b.draws -= 1
                    team_b.points -= 1

        # Apply override
        if action == "completed":
            sets_a, sets_b, games_a, games_b, winner = calculate_match_result(score_a_str, score_b_str)
            if winner is None:
                flash("Invalid score format for override.", "error")
                return redirect(url_for("admin_panel"))
            match.score_a = score_a_str
            match.score_b = score_b_str
            match.sets_a = sets_a
            match.sets_b = sets_b
            match.games_a = games_a
            match.games_b = games_b
            match.status = "completed"
            match.stats_calculated = True
            team_a = Team.query.get(match.team_a_id)
            team_b = Team.query.get(match.team_b_id)
            if team_a and team_b:
                team_a.sets_for += sets_a
                team_a.sets_against += sets_b
                team_a.games_for += games_a
                team_a.games_against += games_b
                team_b.sets_for += sets_b
                team_b.sets_against += sets_a
                team_b.games_for += games_b
                team_b.games_against += games_a
                if winner == 'a':
                    match.winner_id = team_a.id
                    team_a.wins += 1
                    team_a.points += 3
                    team_b.losses += 1
                elif winner == 'b':
                    match.winner_id = team_b.id
                    team_b.wins += 1
                    team_b.points += 3
                    team_a.losses += 1
                else:
                    match.winner_id = None
                    team_a.draws += 1
                    team_b.draws += 1
                    team_a.points += 1
                    team_b.points += 1
        elif action in ("walkover_a", "walkover_b"):
            match.score_a = None
            match.score_b = None
            match.sets_a = 0
            match.sets_b = 0
            match.games_a = 0
            match.games_b = 0
            match.status = "walkover"
            match.stats_calculated = True
            team_a = Team.query.get(match.team_a_id)
            team_b = Team.query.get(match.team_b_id)
            if team_a and team_b:
                if action == "walkover_a":
                    match.winner_id = team_a.id
                    team_a.wins += 1
                    team_a.points += 3
                    team_b.losses += 1
                else:
                    match.winner_id = team_b.id
                    team_b.wins += 1
                    team_b.points += 3
                    team_a.losses += 1
        elif action == "void":
            match.score_a = None
            match.score_b = None
            match.sets_a = 0
            match.sets_b = 0
            match.games_a = 0
            match.games_b = 0
            match.status = "scheduled"
            match.stats_calculated = False
            match.winner_id = None

        if note:
            match.notes = note

        db.session.commit()
        flash(f"Match {match_id} override applied: {action}", "success")
        return redirect(url_for("admin_panel"))

    except Exception as e:
        db.session.rollback()
        flash(f"Error applying override: {str(e)}", "error")
        return redirect(url_for("admin_panel"))


@app.route("/admin/remove-freeagent/<int:freeagent_id>", methods=["POST"])
@require_admin_auth
def remove_freeagent(freeagent_id):
    """Remove a single free agent from the list"""
    free_agent = FreeAgent.query.get_or_404(freeagent_id)

    # Check if this free agent was admin-paired (has partner_id)
    if free_agent.partner_id:
        # Keep history by marking as paired
        free_agent.paired = True
        flash(f"Free agent {free_agent.name} marked as paired (history preserved).", "success")
    else:
        # No partner, safe to delete
        name = free_agent.name
        db.session.delete(free_agent)
        flash(f"Free agent {name} removed from the list.", "success")

    db.session.commit()
    return redirect(url_for("admin_panel"))


@app.route("/admin/remove-ladder-freeagent/<int:freeagent_id>", methods=["POST"])
@require_admin_auth
def remove_ladder_freeagent(freeagent_id):
    """Remove a ladder free agent from the list"""
    free_agent = LadderFreeAgent.query.get_or_404(freeagent_id)
    name = free_agent.name
    
    db.session.delete(free_agent)
    db.session.commit()
    
    flash(f"Free agent {name} removed successfully.", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/edit-free-agent/<int:free_agent_id>", methods=["GET", "POST"])
@require_admin_auth
def edit_free_agent(free_agent_id):
    """Edit free agent registration details"""
    free_agent = FreeAgent.query.get(free_agent_id)
    if not free_agent:
        flash("Free agent not found", "error")
        return redirect(url_for("admin_panel"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        skill_level = request.form.get("skill_level", "").strip()
        playstyle = request.form.get("playstyle", "").strip()
        availability = request.form.get("availability", "").strip()

        errors = []

        if not name:
            errors.append("Name is required")

        if not email:
            errors.append("Email is required")

        if not phone:
            errors.append("Phone number is required")

        if not skill_level:
            errors.append("Skill level is required")

        if not playstyle:
            errors.append("Playstyle is required")

        if not availability:
            errors.append("Availability is required")

        normalized_phone = normalize_phone_number(phone) if phone else None

        if phone and not normalized_phone:
            errors.append("Phone number is invalid")

        if email and not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            errors.append("Email format is invalid")

        if normalized_phone and normalized_phone != free_agent.phone:
            existing_fa_phone = FreeAgent.query.filter_by(phone=normalized_phone).first()
            if existing_fa_phone and existing_fa_phone.id != free_agent_id:
                errors.append("This phone number is already registered")

        if email and email != free_agent.email:
            existing_fa_email = FreeAgent.query.filter_by(email=email).first()
            if existing_fa_email and existing_fa_email.id != free_agent_id:
                errors.append("This email is already registered")

        if errors:
            for error in errors:
                flash(error, "error")
            return render_template("admin_edit_free_agent.html", free_agent=free_agent)

        free_agent.name = name
        free_agent.email = email
        free_agent.phone = normalized_phone
        free_agent.skill_level = skill_level
        free_agent.playstyle = playstyle
        free_agent.availability = availability

        try:
            db.session.commit()
            flash(f"Free agent {name} updated successfully!", "success")
            return redirect(url_for("admin_panel"))
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating free agent: {str(e)}", "error")
            return render_template("admin_edit_free_agent.html", free_agent=free_agent)

    return render_template("admin_edit_free_agent.html", free_agent=free_agent)


@app.route("/admin/cleanup-duplicate-freeagents", methods=["POST"])
@require_admin_auth
def cleanup_duplicate_freeagents():
    """Bulk remove all free agents who are already in teams"""
    free_agents = FreeAgent.query.filter_by(paired=False).all()
    removed_count = 0
    preserved_count = 0

    for fa in free_agents:
        # Check if this free agent exists in a team
        existing_team = Team.query.filter(
            db.or_(
                Team.player1_phone == fa.phone,
                Team.player2_phone == fa.phone,
                Team.player1_email == fa.email,
                Team.player2_email == fa.email
            )
        ).first()

        if existing_team:
            # Check if admin-paired (has partner_id)
            if fa.partner_id:
                # Keep history
                fa.paired = True
                preserved_count += 1
            else:
                # Remove from list
                db.session.delete(fa)
                removed_count += 1

    db.session.commit()

    if removed_count > 0 or preserved_count > 0:
        flash(f"Cleanup complete: {removed_count} free agent(s) removed, {preserved_count} marked as paired (history preserved).", "success")
    else:
        flash("No duplicate free agents found.", "info")

    return redirect(url_for("admin_panel"))


@app.route("/admin/recalculate-player-stats", methods=["POST"])
@require_admin_auth
def admin_recalculate_player_stats():
    """Admin route to recalculate all player stats from completed matches"""
    try:
        matches_count = recalculate_all_player_stats()
        flash(f"Player stats recalculated for {matches_count} completed league matches!", "success")
    except Exception as e:
        flash(f"Error recalculating player stats: {str(e)}", "error")
    
    return redirect(url_for("admin_panel"))


@app.route("/rounds")
def rounds():
    """Display round schedule with Swiss pairing logs (admin only) and playoff bracket"""
    # Get all matches ordered by round
    matches = Match.query.order_by(Match.round, Match.id).all()
    teams = Team.query.all()
    substitutes = Substitute.query.all()

    # Group Swiss rounds (1-5) by round for accordion view
    swiss_rounds_dict = {}
    round_completed_counts = {}
    
    # Knockout bracket data structure
    knockout_bracket = {
        'quarterfinals': [],
        'semifinals': [],
        'final': None,
        'has_matches': False
    }

    # First pass: identify all teams in knockout matches to ensure we can look them up
    # even if they aren't explicitly in the match_data yet
    all_teams_by_id = {t.id: t for t in teams}

    for match in matches:
        if not match.round:
            continue
            
        team_a = db.session.get(Team, match.team_a_id)
        team_b = db.session.get(Team, match.team_b_id) if match.team_b_id else None
        
        match_data = {
            'match': match,
            'team_a': team_a,
            'team_b': team_b
        }
        
        # Swiss rounds (1-5) go to accordion
        if match.round <= 5:
            if match.round not in swiss_rounds_dict:
                swiss_rounds_dict[match.round] = []
                round_completed_counts[match.round] = 0

            swiss_rounds_dict[match.round].append(match_data)
            
            # Count completed matches (including walkovers)
            if match.status in ('completed', 'walkover'):
                round_completed_counts[match.round] += 1
                
        # Knockout rounds (6+) go to bracket
        elif match.round >= 6:
            knockout_bracket['has_matches'] = True
            
            if match.phase == 'quarterfinal' or match.round == 6:
                knockout_bracket['quarterfinals'].append(match_data)
            elif match.phase == 'semifinal' or match.round == 7:
                # Ensure team_a and team_b are populated from IDs if they were advanced
                if not match_data['team_a'] and match.team_a_id:
                    match_data['team_a'] = all_teams_by_id.get(match.team_a_id)
                if not match_data['team_b'] and match.team_b_id:
                    match_data['team_b'] = all_teams_by_id.get(match.team_b_id)
                knockout_bracket['semifinals'].append(match_data)
            elif match.phase == 'final' or match.round == 8:
                # Ensure team_a and team_b are populated from IDs if they were advanced
                if not match_data['team_a'] and match.team_a_id:
                    match_data['team_a'] = all_teams_by_id.get(match.team_a_id)
                if not match_data['team_b'] and match.team_b_id:
                    match_data['team_b'] = all_teams_by_id.get(match.team_b_id)
                knockout_bracket['final'] = match_data
    
    # Sort knockout matches by bracket_slot for proper bracket order
    def slot_sort_key(m):
        slot = m['match'].bracket_slot or ''
        # Extract number from slot (e.g., "QF1" -> 1, "SF2" -> 2)
        import re
        num = re.search(r'\d+', slot)
        return int(num.group()) if num else 0
    
    knockout_bracket['quarterfinals'].sort(key=slot_sort_key)
    knockout_bracket['semifinals'].sort(key=slot_sort_key)

    # Build derived SF/Finals slots from QF winners (READ-ONLY, no DB writes)
    # This allows bracket visualization even before SF round is generated
    qf_winners = {}
    for qf_data in knockout_bracket['quarterfinals']:
        qf_match = qf_data['match']
        if qf_match.bracket_slot and qf_match.winner_id:
            qf_winners[qf_match.bracket_slot] = qf_match.winner_id
    
    # Derived semi-final slots (purely visual, not from DB)
    derived_sf_slots = {
        'SF1': {
            'team_a': all_teams_by_id.get(qf_winners.get('QF1')),
            'team_b': all_teams_by_id.get(qf_winners.get('QF2'))
        },
        'SF2': {
            'team_a': all_teams_by_id.get(qf_winners.get('QF3')),
            'team_b': all_teams_by_id.get(qf_winners.get('QF4'))
        }
    }
    
    # Derived finals slot (from SF winners if SF matches exist and are complete)
    sf_winners = {}
    for sf_data in knockout_bracket['semifinals']:
        sf_match = sf_data['match']
        if sf_match.bracket_slot and sf_match.winner_id:
            sf_winners[sf_match.bracket_slot] = sf_match.winner_id
    
    derived_final_slot = {
        'team_a': all_teams_by_id.get(sf_winners.get('SF1')),
        'team_b': all_teams_by_id.get(sf_winners.get('SF2'))
    }

    return render_template(
        "rounds.html",
        rounds_dict=swiss_rounds_dict,
        round_completed_counts=round_completed_counts,
        knockout_bracket=knockout_bracket,
        derived_sf_slots=derived_sf_slots,
        derived_final_slot=derived_final_slot,
        teams=teams,
        substitutes=substitutes
    )

@app.route("/rules")
def rules():
    return render_template("rules.html")



# Error Handlers for Production
@app.errorhandler(404)
def page_not_found(e):
    """Handle 404 errors"""
    return render_template('base.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    """Handle 500 errors"""
    db.session.rollback()
    return render_template('base.html'), 500

# Production Configuration
def setup_production():
    """Setup production-specific configurations"""
    import logging

    # Set up logging
    if not app.debug:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        )
        app.logger.setLevel(logging.INFO)
        app.logger.info('Padel League Hub startup')

    # Optional: Initialize Sentry for error monitoring
    # Uncomment if you've added sentry-sdk to requirements.txt
    # sentry_dsn = os.environ.get("SENTRY_DSN")
    # if sentry_dsn:
    #     import sentry_sdk
    #     from sentry_sdk.integrations.flask import FlaskIntegration
    #     sentry_sdk.init(
    #         dsn=sentry_dsn,
    #         integrations=[FlaskIntegration()],
    #         traces_sample_rate=0.1,
    #         environment=os.environ.get("ENVIRONMENT", "production")
    #     )
    #     app.logger.info('Sentry error monitoring initialized')

# Initialize production setup (non-blocking)
setup_production()

# Lazy database initialization - only run when needed
def init_db():
    """Initialize database tables if needed (safe for existing databases)"""
    try:
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        existing_tables = inspector.get_table_names()

        # Only create tables if database is empty
        if not existing_tables:
            with app.app_context():
                db.create_all()
                app.logger.info("Database tables created")
        else:
            app.logger.info(f"Database already initialized with {len(existing_tables)} tables")
        return True
    except Exception as e:
        app.logger.error(f"Database initialization failed: {e}")
        app.logger.error("Application will continue but database features may not work")
        return False

# Initialize DB in background on first request (non-blocking for health checks)
_db_initialized = False
_db_available = True

@app.before_request
def ensure_db_initialized():
    """Ensure database is initialized before processing requests"""
    global _db_initialized, _db_available

    # Skip health check - it must work without database
    if request.endpoint == 'health':
        return

    # Try to initialize database on first non-health request
    if not _db_initialized:
        _db_available = init_db()
        _db_initialized = True

        if not _db_available:
            app.logger.warning("Database not available - some features will not work")


@app.route("/ladder/score/confirm/<int:match_id>", methods=["POST"])
def ladder_score_confirm(match_id):
    """Confirm opponent's submitted score"""
    from utils import send_email_notification
    
    token = request.form.get("token")
    team = LadderTeam.query.filter_by(access_token=token).first_or_404()
    match = LadderMatch.query.get_or_404(match_id)
    
    if match.team_a_id != team.id and match.team_b_id != team.id:
        flash("Unauthorized", "error")
        return redirect(url_for('ladder_my_team', token=token))
    
    is_team_a = (match.team_a_id == team.id)
    
    if is_team_a:
        match.score_confirmed_by_a = True
        match.team_a_submitted = True  # Confirm counts as submission
    else:
        match.score_confirmed_by_b = True
        match.team_b_submitted = True  # Confirm counts as submission
    
    db.session.commit()
    
    # Check if both teams have submitted (submission counts as confirmation)
    if match.team_a_submitted and match.team_b_submitted:
        # Both teams submitted - verify and complete
        if verify_match_scores(match):
            flash("Both teams confirmed! Match completed.", "success")
        else:
            flash("Scores need admin review due to mismatch.", "warning")
    else:
        match.status = 'score_confirmed'
        db.session.commit()
        flash("Score confirmed. Waiting for opponent.", "success")
    
    return redirect(url_for('ladder_my_team', token=token))


@app.route("/ladder/score/reject/<int:match_id>", methods=["POST"])
def ladder_score_reject(match_id):
    """Reject opponent's score and allow resubmission"""
    from utils import send_email_notification
    
    token = request.form.get("token")
    team = LadderTeam.query.filter_by(access_token=token).first_or_404()
    match = LadderMatch.query.get_or_404(match_id)
    
    if match.team_a_id != team.id and match.team_b_id != team.id:
        flash("Unauthorized", "error")
        return redirect(url_for('ladder_my_team', token=token))
    
    match.rejection_count = (match.rejection_count or 0) + 1
    
    if match.rejection_count >= 2:
        match.status = 'disputed'
        match.disputed = True
        db.session.commit()
        flash("Both teams rejected scores - escalated to admin.", "warning")
    else:
        is_team_a = (match.team_a_id == team.id)
        
        if is_team_a:
            match.team_b_submitted = False
            match.score_confirmed_by_b = False
        else:
            match.team_a_submitted = False
            match.score_confirmed_by_a = False
        
        match.status = 'pending_opponent_score'
        db.session.commit()
        
        opponent_team = LadderTeam.query.get(match.team_b_id if is_team_a else match.team_a_id)
        
        rejection_message = f"""
Score Rejected

{team.team_name} rejected your submitted score. Please resubmit your score.

If you reject again, match will go to admin review.

Manage your team: {request.url_root}ladder/my-team/{opponent_team.access_token}

BD Padel Ladder Team
"""
        
        if opponent_team.contact_preference_email:
            if opponent_team.player1_email:
                send_email_notification(opponent_team.player1_email, "Score Rejected - Resubmit", rejection_message)
            if opponent_team.player2_email and opponent_team.player2_email != opponent_team.player1_email:
                send_email_notification(opponent_team.player2_email, "Score Rejected - Resubmit", rejection_message)
        
        flash("Score rejected. Opponent will resubmit.", "info")
    
    return redirect(url_for('ladder_my_team', token=token))

if __name__ == "__main__":
    # Development mode only
    port = int(os.environ.get("PORT") or 5000)
    debug = os.environ.get("FLASK_ENV") == "development"
    app.run(host="0.0.0.0", port=port, debug=debug)