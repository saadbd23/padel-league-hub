from flask import Flask, render_template, redirect, url_for, request, flash, session
import os
import secrets
import re
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
from models import db, Team, FreeAgent, Match, Reschedule, Substitute, Player, LeagueSettings
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
    "pool_recycle": 300,     # Recycle connections after 5 minutes
    "pool_size": 3,          # Limit to 3 connections max (conservative for free tier)
    "max_overflow": 2,       # Allow 2 extra connections in burst
    "pool_timeout": 30,      # Wait up to 30s for a connection from pool
    "connect_args": {
        "connect_timeout": 10,  # 10 second connection timeout
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
    
    # Mark stats as calculated
    match.stats_calculated = True


def update_player_stats_from_match(match, team_a, team_b):
    """Update individual player statistics based on match result"""
    # Get unique players from both teams (avoid duplicates)
    players_a = []
    players_b = []
    
    # Get Team A players (avoid duplicates)
    player1_a = Player.query.filter_by(phone=team_a.player1_phone).first()
    if player1_a:
        players_a.append(player1_a)
    
    if team_a.player2_phone != team_a.player1_phone:
        player2_a = Player.query.filter_by(phone=team_a.player2_phone).first()
        if player2_a:
            players_a.append(player2_a)
    
    # Get Team B players (avoid duplicates)
    player1_b = Player.query.filter_by(phone=team_b.player1_phone).first()
    if player1_b:
        players_b.append(player1_b)
    
    if team_b.player2_phone != team_b.player1_phone:
        player2_b = Player.query.filter_by(phone=team_b.player2_phone).first()
        if player2_b:
            players_b.append(player2_b)
    
    # Update player stats for Team A
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
        else:
            player.draws += 1
            player.points += 1
    
    # Update player stats for Team B
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
        else:
            player.draws += 1
            player.points += 1


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


def get_round_date_range(round_number):
    """Calculate the Monday-Sunday date range for a given round number"""
    if not round_number:
        return None
    
    from datetime import datetime, timedelta
    
    # Calculate the start date (Monday) for the round
    # Assuming Round 1 starts from a specific Monday (you can adjust this)
    # For now, let's assume Round 1 starts from the first Monday of 2025
    round_1_start = datetime(2025, 11, 17)  # November 17, 2025 (first Monday)
    round_start = round_1_start + timedelta(weeks=round_number - 1)
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
    # 1. Check MAKEUP MATCH deadlines (Wednesday 23:59)
    # ========================================
    pending_reschedules = get_pending_reschedules()
    
    for reschedule in pending_reschedules:
        # Parse the proposed time
        if reschedule.proposed_time and " at " in reschedule.proposed_time:
            date_str = reschedule.proposed_time.split(" at ")[0]
            try:
                proposed_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                
                # Check if it's a Monday/Tuesday/Wednesday date
                proposed_weekday = proposed_date.weekday()
                if proposed_weekday in [0, 1, 2]:  # Mon, Tue, Wed
                    # Find the Wednesday of that week
                    days_to_wednesday = 2 - proposed_weekday
                    wednesday_of_week = proposed_date + timedelta(days=days_to_wednesday)
                    
                    # Wednesday deadline is 23:59
                    wednesday_deadline = datetime.combine(wednesday_of_week, datetime.max.time())
                    
                    # Check if deadline has passed
                    if now > wednesday_deadline:
                        # Get the match
                        match = Match.query.get(reschedule.match_id)
                        if match and match.status != "completed":
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
                                    # Opponent is Team A, they win 6-0, 6-0
                                    match.score_a = "6-0, 6-0"
                                    match.score_b = "0-6, 0-6"
                                    match.sets_a = 2
                                    match.sets_b = 0
                                    match.games_a = 12
                                    match.games_b = 0
                                else:
                                    # Opponent is Team B, they win 6-0, 6-0
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
                                    'deadline': wednesday_deadline.strftime("%A, %B %d at %H:%M"),
                                    'type': 'makeup'
                                })
                                
            except ValueError:
                # Invalid date format, skip
                continue
    
    # ========================================
    # 2. Check REGULAR MATCH deadlines (Sunday 23:59)
    # ========================================
    # Get all non-completed matches that don't have pending reschedules
    rescheduled_match_ids = [r.match_id for r in pending_reschedules]
    
    # Find matches that should have been completed by last Sunday
    all_matches = Match.query.filter(Match.status != "completed").all()
    
    for match in all_matches:
        # Skip if this match has a pending reschedule (it gets Wednesday deadline)
        if match.id in rescheduled_match_ids:
            continue
        
        # Skip if match doesn't have a round or match_date
        if not match.round:
            continue
        
        # Calculate the Sunday deadline for this round
        # Assuming rounds start on Monday, we need to find the Sunday of that week
        round_start_date = get_round_start_date(match.round)
        if round_start_date:
            # Find the Sunday of that week (6 days after Monday)
            sunday_of_week = round_start_date + timedelta(days=6)
            sunday_deadline = datetime.combine(sunday_of_week, datetime.max.time())
            
            # Check if deadline has passed
            if now > sunday_deadline:
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
                        'deadline': sunday_deadline.strftime("%A, %B %d at %H:%M"),
                        'type': 'regular'
                    })
    
    if walkovers_applied['regular'] or walkovers_applied['makeup']:
        db.session.commit()
    
    return walkovers_applied


def get_round_start_date(round_number):
    """
    Calculate the Monday start date for a given round number
    Round 1 starts January 6, 2025 (first Monday)
    """
    from datetime import datetime, timedelta
    if not round_number:
        return None
    round_1_start = datetime(2025, 1, 6).date()  # January 6, 2025 (Monday)
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
    teams = Team.query.count()
    free_agents = FreeAgent.query.filter_by(paired=False).count()
    return render_template("index.html", teams=teams, free_agents=free_agents)

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
    # Check if free agent registration is open
    settings = LeagueSettings.query.first()
    if settings and not settings.freeagent_registration_open:
        return render_template("registration_closed.html", registration_type="Free Agent")
    
    if request.method == "POST":
        name = request.form["name"]
        phone = request.form["phone"]
        email = request.form.get("email", "").strip()
        skill = request.form["skill_level"]
        style = request.form["playstyle"]
        avail = request.form["availability"]

        # Require email
        if not email:
            flash("Email is required for free agent registration.", "error")
            return render_template("register_freeagent.html", form_data=request.form)

        # Normalize phone number
        phone_normalized = normalize_phone_number(phone)

        # Check if email is already registered in a team
        existing_team_email = Team.query.filter(
            db.or_(
                Team.player1_email == email,
                Team.player2_email == email
            )
        ).first()
        
        if existing_team_email:
            flash(f"This email ({email}) is already registered in team '{existing_team_email.team_name}'. Please use a different email.", "error")
            return render_template("register_freeagent.html", form_data=request.form)

        # Check if phone number is already registered in a team
        existing_team_phone = Team.query.filter(
            db.or_(
                Team.player1_phone == phone_normalized,
                Team.player2_phone == phone_normalized
            )
        ).first()
        
        if existing_team_phone:
            flash(f"This WhatsApp number is already registered in team '{existing_team_phone.team_name}'. Please use a different number.", "error")
            return render_template("register_freeagent.html", form_data=request.form)

        # Check if email or phone is already registered as a free agent
        existing_fa_email = FreeAgent.query.filter_by(email=email).first()
        if existing_fa_email:
            flash(f"This email is already registered as a free agent. Please use a different email.", "error")
            return render_template("register_freeagent.html", form_data=request.form)

        existing_fa_phone = FreeAgent.query.filter_by(phone=phone_normalized).first()
        if existing_fa_phone:
            flash(f"This WhatsApp number is already registered as a free agent. Please use a different number.", "error")
            return render_template("register_freeagent.html", form_data=request.form)

        fa = FreeAgent(name=name, phone=phone_normalized, email=email,
                       skill_level=skill, playstyle=style, availability=avail)
        db.session.add(fa)
        db.session.commit()
        
        # Send admin notification about new free agent registration
        admin_email = os.environ.get("ADMIN_EMAIL")
        if admin_email:
            from utils import send_email_notification
            admin_body = f"""🆕 NEW FREE AGENT REGISTRATION

Name: {name}
Email: {email}
Phone: {phone}
Skill Level: {skill}
Playstyle: {style}
Availability: {avail}

Please review and pair this free agent in the admin panel.
"""
            send_email_notification(admin_email, f"New Free Agent: {name}", admin_body)
        
        # Send welcome email to free agent
        if email:
            from utils import send_email_notification
            email_body = f"""Hi {name},

✅ Welcome to BD Padel League! Your free agent registration has been confirmed.

📋 Your Profile:
- Name: {name}
- Skill Level: {skill}
- Playstyle: {style}
- Availability: {avail}

🤝 What's Next?
Our admin team will review all free agent registrations and pair you with another player of similar skill level. Once paired, you'll receive:
- A confirmation email with your team details
- Your partner's contact information
- Access to your team page to view matches

⏳ This process typically takes 1-3 days, depending on the number of free agents.

💬 Join Our WhatsApp Community for Free Agents:
https://chat.whatsapp.com/KCdAt3a5YbSCHF6wKauIQq

Connect with other free agents, find potential partners, and stay updated!

If you have any questions or want to update your profile, please contact the admin.

Thank you for joining the league! 🎾

- BD Padel League
"""
            send_email_notification(email, f"Free Agent Registration Confirmed - BD Padel League", email_body)
        
        flash("Free Agent registered successfully!")
        return redirect(url_for("index"))
    return render_template("register_freeagent.html")

@app.route("/leaderboard")
def leaderboard():
    """
    Leaderboard with proper padel league ranking:
    1. Points (3 for win, 1 for draw, 0 for loss)
    2. Sets difference
    3. Games difference  
    4. Wins
    5. Team name (alphabetical)
    """
    teams = Team.query.order_by(
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
    Player leaderboard with individual statistics
    Sorted by: Points > Win % > Matches Played > Sets Diff > Games Diff
    """
    players = Player.query.filter(Player.matches_played > 0).order_by(
        Player.points.desc(),
        Player.wins.desc(),
        Player.matches_played.desc(),
        (Player.sets_for - Player.sets_against).desc(),
        (Player.games_for - Player.games_against).desc(),
        Player.name
    ).all()
    return render_template("player_leaderboard.html", players=players)

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
        recent_form=recent_form
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
        match.round_dates = get_round_date_range(match.round)
        
        match_details.append({
            'match': match,
            'opponent': opponent,
            'is_team_a': match.team_a_id == team.id
        })
    
    return render_template(
        "my_matches.html",
        team=team,
        match_details=match_details
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
        
        # Get opponent
        opponent_id = match.team_b_id if match.team_a_id == team.id else match.team_a_id
        opponent = Team.query.get(opponent_id)
        
        # Check if opponent already submitted the same booking
        if match.booking_details:
            # Parse existing booking
            try:
                existing_datetime_str = match.booking_details.split("Court assigned on arrival")[0].strip()
                if datetime_str in existing_datetime_str:
                    # Both teams agree! Confirm booking
                    match.match_datetime = match_datetime
                    match.match_date = match_datetime.strftime("%A, %B %d at %I:%M %p")
                    match.court = "Court assigned on arrival"
                    match.booking_confirmed = True
                    match.booking_details = f"{match.match_date}\nCourt assigned on arrival\n✓ Confirmed by both teams"
                    db.session.commit()
                    
                    # Send confirmation emails
                    confirmation_body = f"""Hi!

Your match booking has been confirmed by both teams:

Match: {team.team_name} vs {opponent.team_name}
Date & Time: {match.match_date}
Court: Assigned on arrival

See you on the court! 🎾

- BD Padel League
"""
                    if team.player1_email:
                        send_email_notification(team.player1_email, "Match Booking Confirmed", confirmation_body)
                    if team.player2_email:
                        send_email_notification(team.player2_email, "Match Booking Confirmed", confirmation_body)
                    if opponent.player1_email:
                        send_email_notification(opponent.player1_email, "Match Booking Confirmed", confirmation_body)
                    if opponent.player2_email:
                        send_email_notification(opponent.player2_email, "Match Booking Confirmed", confirmation_body)
                    
                    return {
                        "success": True,
                        "message": "Booking confirmed by both teams!",
                        "confirmed": True,
                        "booking_details": match.booking_details
                    }
            except:
                pass
        
        # Store this team's booking (waiting for opponent confirmation)
        formatted_datetime = match_datetime.strftime("%A, %B %d at %I:%M %p")
        match.booking_details = f"{formatted_datetime}\nCourt assigned on arrival\nWaiting for {opponent.team_name} to confirm..."
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
            
            # Convert to datetime object
            match_datetime = datetime.strptime(datetime_str, "%A, %B %d at %I:%M %p")
            
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
Date & Time: {datetime_str}
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
                
                # Update all stats (team + player) using centralized function
                from utils import verify_match_and_calculate_stats
                verify_match_and_calculate_stats(match, team_a, team_b, db.session)
                
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
        
        # Check reschedule limit (max 2 per team)
        if team.reschedules_used >= 2:
            return {
                "success": False, 
                "message": "Your team has already used all 2 reschedules. Contact admin for special approval."
            }, 400
        
        # Check if we've reached the round reschedule limit
        pending_reschedules = get_pending_reschedules()
        max_per_round = get_max_reschedules_per_round()
        
        if len(pending_reschedules) >= max_per_round:
            return {
                "success": False,
                "message": f"Maximum reschedule limit reached for this round ({max_per_round} reschedules). Please wait for admin to process pending requests or contact admin for special approval."
            }, 400
        
        # Validate reschedule request is before Wednesday cutoff
        from datetime import datetime, timedelta
        today = datetime.now().date()
        current_weekday = today.weekday()  # 0 = Monday, 6 = Sunday
        
        # Check if today is Thursday, Friday, Saturday, or Sunday
        if current_weekday >= 3:  # Thursday (3) or later
            return {
                "success": False,
                "message": "Reschedule requests can only be submitted Monday-Wednesday of the current round. It's too late to reschedule this round. Please contact admin for emergency situations."
            }, 400
        
        # Calculate next Monday (start of following week)
        current_weekday = today.weekday()  # 0 = Monday, 1 = Tuesday, etc.
        
        if current_weekday == 0:  # If today is Monday, next Monday is 7 days away
            days_until_next_monday = 7
        else:
            # Calculate days until next Monday
            days_until_next_monday = (7 - current_weekday) % 7
            if days_until_next_monday == 0:
                days_until_next_monday = 7
        
        next_monday = today + timedelta(days=days_until_next_monday)
        
        # Calculate next Wednesday (CHANGED from Sunday to Wednesday)
        next_wednesday = next_monday + timedelta(days=2)
        
        selected_date = datetime.strptime(date, "%Y-%m-%d").date()
        if selected_date < next_monday or selected_date > next_wednesday:
            return {
                "success": False,
                "message": f"Reschedule date must be Monday-Wednesday of next week only ({next_monday.strftime('%Y-%m-%d')} to {next_wednesday.strftime('%Y-%m-%d')})"
            }, 400
        
        # Additional validation: Selected day must be Mon, Tue, or Wed
        selected_weekday = selected_date.weekday()  # 0 = Monday, 1 = Tuesday, 2 = Wednesday
        if selected_weekday not in [0, 1, 2]:
            return {
                "success": False,
                "message": "Match can only be rescheduled to Monday, Tuesday, or Wednesday. Wednesday 23:59 is the absolute deadline."
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
        
        # Calculate Wednesday deadline for notification
        selected_date_obj = datetime.strptime(date, "%Y-%m-%d").date()
        selected_weekday = selected_date_obj.weekday()
        days_to_wednesday = 2 - selected_weekday
        wednesday_deadline = selected_date_obj + timedelta(days=days_to_wednesday)
        
        deadline_text = f"⚠️ MAKEUP MATCH DEADLINE: Wednesday {wednesday_deadline.strftime('%B %d')} 23:59"
        
        # Send email notifications to both teams
        from utils import send_email_notification
        opponent_id = match.team_b_id if match.team_a_id == team.id else match.team_a_id
        opponent = Team.query.get(opponent_id)
        
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
        
        if not all([match_id, sub_name, sub_phone, sub_email]):
            return {"success": False, "message": "Match ID, substitute name, phone, and email are required"}, 400
        
        # Find the match
        match = Match.query.get(match_id)
        if not match:
            return {"success": False, "message": "Match not found"}, 404
        
        # Verify team is part of this match
        if match.team_a_id != team.id and match.team_b_id != team.id:
            return {"success": False, "message": "Unauthorized"}, 403
        
        # Check substitute limit (max 2 per team in league stage)
        if team.subs_used >= 2:
            return {
                "success": False,
                "message": "Your team has already used all 2 substitutes. No more subs allowed in league stage."
            }, 400
        
        # Create substitute request
        from datetime import datetime
        s = Substitute(
            team_id=team.id,
            match_id=match_id,
            name=sub_name,
            phone=sub_phone,
            email=sub_email,
            status="pending",
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        db.session.add(s)
        db.session.commit()
        
        # Send notifications to all parties
        from utils import send_email_notification
        
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

Admin will review and approve/deny the request soon. You will receive a confirmation email once processed.

Thank you!
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
    
    return render_template(
        "stats.html",
        teams=teams,
        team_streaks=team_streaks,
        teams_by_points=teams_by_points,
        teams_by_sets_diff=teams_by_sets_diff,
        teams_by_games_diff=teams_by_games_diff,
        teams_by_wins=teams_by_wins,
        teams_by_streak=teams_by_streak,
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
    matches = Match.query.all()
    reschedules = Reschedule.query.filter_by(status="pending").all()
    substitutes = Substitute.query.filter_by(status="pending").all()
    # History (approved/denied)
    reschedules_history = Reschedule.query.filter(Reschedule.status != "pending").all()
    substitutes_history = Substitute.query.filter(Substitute.status != "pending").all()
    
    # Get reschedule data for dashboard
    pending_reschedules_count = len(reschedules)
    max_reschedules = get_max_reschedules_per_round()
    
    # Calculate current and next round numbers
    current_round = 0
    if matches:
        # Get the highest round number from existing matches
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
    
    return render_template(
        "admin.html",
        teams=teams,
        free_agents=free_agents,
        free_agent_status=free_agent_status,
        matches=matches,
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
        current_round=current_round,
        next_round=next_round,
    )


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


@app.route("/admin/pair-agents", methods=["POST"])
@require_admin_auth
def pair_agents():
    agent1_id = request.form.get("agent1_id")
    agent2_id = request.form.get("agent2_id")
    team_name = request.form.get("team_name")

    agent1 = FreeAgent.query.get(agent1_id)
    agent2 = FreeAgent.query.get(agent2_id)

    if agent1 and agent2:
        # Generate unique access token for this team
        access_token = secrets.token_urlsafe(32)
        
        new_team = Team(
            team_name=team_name,
            player1_name=agent1.name,
            player1_phone=agent1.phone,
            player1_email=agent1.email,
            player2_name=agent2.name,
            player2_phone=agent2.phone,
            player2_email=agent2.email,
            access_token=access_token,
            confirmed=True,
            player2_confirmed=True
        )
        agent1.paired = True
        agent1.partner_id = agent2_id
        agent2.paired = True
        agent2.partner_id = agent1_id

        db.session.add(new_team)
        db.session.commit()
        
        # Send email notifications to both free agents
        from utils import send_email_notification
        base_url = "https://goeclectic.xyz"
        access_link = f"{base_url}/my-matches/{access_token}"
        
        # Email to Agent 1
        if agent1.email:
            email_body1 = f"""Hi {agent1.name},

🎉 GREAT NEWS! You've been paired with a partner!

Team Details:
- Team Name: {team_name}
- Your Partner: {agent2.name}
- Partner Email: {agent2.email}
- Partner Phone: {agent2.phone}

🔗 Your Team Access Link:
{access_link}

Use this link to:
- View your match schedule
- See opponent contact information
- Submit match scores
- Request reschedules or substitutes

💬 Join Our WhatsApp Community:
https://chat.whatsapp.com/FGOQG62XwWfDazc6ZmMagT

Stay connected with other teams, get updates, and coordinate matches!

Please reach out to your partner to introduce yourself and get ready to compete!

Good luck in the league! 🎾

- BD Padel League
"""
            send_email_notification(agent1.email, f"You've Been Paired! - Team {team_name}", email_body1)
        
        # Email to Agent 2
        if agent2.email:
            email_body2 = f"""Hi {agent2.name},

🎉 GREAT NEWS! You've been paired with a partner!

Team Details:
- Team Name: {team_name}
- Your Partner: {agent1.name}
- Partner Email: {agent1.email}
- Partner Phone: {agent1.phone}

🔗 Your Team Access Link:
{access_link}

Use this link to:
- View your match schedule
- See opponent contact information
- Submit match scores
- Request reschedules or substitutes

💬 Join Our WhatsApp Community:
https://chat.whatsapp.com/FGOQG62XwWfDazc6ZmMagT

Stay connected with other teams, get updates, and coordinate matches!

Please reach out to your partner to introduce yourself and get ready to compete!

Good luck in the league! 🎾

- BD Padel League
"""
            send_email_notification(agent2.email, f"You've Been Paired! - Team {team_name}", email_body2)
        
        flash("Free agents paired successfully! Email notifications sent to both players.", "success")
    else:
        flash("Error pairing agents", "error")

    return redirect(url_for("admin_panel"))

@app.route("/admin/generate-round", methods=["POST"])
@require_admin_auth
def generate_round():
    round_number = request.form.get("round_number", type=int)
    if not round_number:
        flash("Please provide a round number", "error")
        return redirect(url_for("admin_panel"))
    
    # Check if playoffs are approved
    settings = LeagueSettings.query.first()
    if settings and settings.playoffs_approved and settings.current_phase == "playoffs":
        # PLAYOFF GENERATION MODE
        # Determine which playoff phase to generate
        quarterfinals = Match.query.filter_by(phase="quarterfinal").all()
        semifinals = Match.query.filter_by(phase="semifinal").all()
        third_place = Match.query.filter_by(phase="third_place").first()
        final = Match.query.filter_by(phase="final").first()
        
        try:
            phase_name = ""
            if not quarterfinals and settings.playoff_teams_count >= 8:
                # Generate quarterfinals
                matches = generate_playoff_bracket(round_number, "quarterfinal")
                phase_name = "Quarterfinals"
                flash(f"✅ Quarterfinals generated! {len(matches)} matches created.", "success")
            elif not semifinals and (quarterfinals or settings.playoff_teams_count < 8):
                # Generate semifinals
                matches = generate_playoff_bracket(round_number, "semifinal")
                phase_name = "Semifinals"
                flash(f"✅ Semifinals generated! {len(matches)} matches created.", "success")
            elif semifinals and not third_place and not final:
                # Generate both third place and final (same round)
                third_place_matches = generate_playoff_bracket(round_number, "third_place")
                final_matches = generate_playoff_bracket(round_number, "final")
                matches = third_place_matches + final_matches
                phase_name = "Finals"
                flash(f"✅ Finals generated! 3rd Place Match and Championship Final created.", "success")
            else:
                flash("All playoff rounds have already been generated!", "warning")
                return redirect(url_for("admin_panel"))
            
            # Send playoff email notifications
            from utils import send_email_notification
            base_url = "https://goeclectic.xyz"
            
            for match in matches:
                team_a = Team.query.get(match.team_a_id)
                team_b = Team.query.get(match.team_b_id)
                
                if not team_a or not team_b:
                    continue
                
                # Determine playoff stage description
                stage_emoji = "🏆"
                stage_desc = ""
                if match.phase == "quarterfinal":
                    stage_emoji = "⚡"
                    stage_desc = "QUARTERFINAL - Single Elimination"
                elif match.phase == "semifinal":
                    stage_emoji = "🔥"
                    stage_desc = "SEMIFINAL - One Step From Glory"
                elif match.phase == "third_place":
                    stage_emoji = "🥉"
                    stage_desc = "3RD PLACE MATCH - Battle for Bronze"
                elif match.phase == "final":
                    stage_emoji = "👑"
                    stage_desc = "CHAMPIONSHIP FINAL - Winner Takes All"
                
                # Team A notification
                team_a_link = f"{base_url}/my-matches/{team_a.access_token}"
                team_a_body = f"""Hi {team_a.team_name},

{stage_emoji} PLAYOFF MATCH GENERATED {stage_emoji}

🎯 {stage_desc}

Your Match:
- Opponent: {team_b.team_name}
- Format: Best of 3 Sets (Win 2 Sets to Advance)
- Round: {round_number}

{"🏆 THIS IS IT! The Championship Final! Winner becomes the league champion!" if match.phase == "final" else "⚠️ This is single elimination - you must win to advance to the next round!" if match.phase in ["quarterfinal", "semifinal"] else ""}

📋 Next Steps:
1. Coordinate with your opponent to book a court
2. Play your match before the deadline
3. Submit scores immediately after the match

🔗 Your Match Page: {team_a_link}

Opponent Contact:
- {team_b.player1_name}: {team_b.player1_email or team_b.player1_phone}
- {team_b.player2_name}: {team_b.player2_email or team_b.player2_phone}

Good luck! May the best team win! 🏆

- BD Padel League
"""
                if team_a.player1_email:
                    send_email_notification(team_a.player1_email, f"{stage_emoji} PLAYOFF: {stage_desc}", team_a_body)
                if team_a.player2_email:
                    send_email_notification(team_a.player2_email, f"{stage_emoji} PLAYOFF: {stage_desc}", team_a_body)
                
                # Team B notification
                team_b_link = f"{base_url}/my-matches/{team_b.access_token}"
                team_b_body = f"""Hi {team_b.team_name},

{stage_emoji} PLAYOFF MATCH GENERATED {stage_emoji}

🎯 {stage_desc}

Your Match:
- Opponent: {team_a.team_name}
- Format: Best of 3 Sets (Win 2 Sets to Advance)
- Round: {round_number}

{"🏆 THIS IS IT! The Championship Final! Winner becomes the league champion!" if match.phase == "final" else "⚠️ This is single elimination - you must win to advance to the next round!" if match.phase in ["quarterfinal", "semifinal"] else ""}

📋 Next Steps:
1. Coordinate with your opponent to book a court
2. Play your match before the deadline
3. Submit scores immediately after the match

🔗 Your Match Page: {team_b_link}

Opponent Contact:
- {team_a.player1_name}: {team_a.player1_email or team_a.player1_phone}
- {team_a.player2_name}: {team_a.player2_email or team_a.player2_phone}

Good luck! May the best team win! 🏆

- BD Padel League
"""
                if team_b.player1_email:
                    send_email_notification(team_b.player1_email, f"{stage_emoji} PLAYOFF: {stage_desc}", team_b_body)
                if team_b.player2_email:
                    send_email_notification(team_b.player2_email, f"{stage_emoji} PLAYOFF: {stage_desc}", team_b_body)
            
            return redirect(url_for("admin_panel"))
        
        except Exception as e:
            flash(f"Error generating playoff round: {str(e)}", "error")
            return redirect(url_for("admin_panel"))
    
    # SWISS ROUND GENERATION MODE
    # Check for deadline violations and apply walkovers
    walkovers = check_deadline_violations()
    
    # Show regular deadline violations (Sunday)
    if walkovers['regular']:
        for walkover in walkovers['regular']:
            flash(f"⚠️ Sunday Deadline Missed: {walkover['team_a']} vs {walkover['team_b']} - Round {walkover['round']} (walkover awarded)", "warning")
    
    # Show makeup deadline violations (Wednesday)
    if walkovers['makeup']:
        for walkover in walkovers['makeup']:
            flash(f"⚠️ Makeup Match Deadline Missed: {walkover['opponent_team']} wins vs {walkover['requester_team']} (missed Wednesday deadline)", "warning")
    
    # Check for pending reschedules - WARNING ONLY, not a hard block
    pending_reschedules = get_pending_reschedules()
    max_allowed = get_max_reschedules_per_round()
    
    if len(pending_reschedules) > 0:
        flash(f"ℹ️ Note: {len(pending_reschedules)} makeup match(es) pending. These teams will play 2 matches this week (1 makeup + 1 new round).", "info")
        if len(pending_reschedules) > max_allowed:
            flash(f"⚠️ Warning: Pending makeup matches ({len(pending_reschedules)}) exceed recommended limit ({max_allowed}).", "warning")
    
    # Generate round with reschedule checking
    try:
        matches = generate_round_pairings(round_number)
        
        # Check for conflicts with pending reschedules
        conflicts = check_reschedule_conflicts(matches)
        
        if conflicts:
            conflict_details = []
            for conflict in conflicts:
                conflict_details.append(f"Team {conflict['conflicting_teams'][0]} and {conflict['conflicting_teams'][1]} have pending reschedules")
            
            flash(f"Round {round_number} generated with {len(matches)} matches, but {len(conflicts)} team(s) have pending makeup matches. They will play 2 matches this week.", "warning")
        else:
            flash(f"✅ Round {round_number} generated with {len(matches)} matches! No conflicts with pending reschedules.", "success")
            
        # Add round date information to matches
        for match in matches:
            match.round_dates = get_round_date_range(round_number)
        
        # Send email notifications to all teams about new round pairings
        from utils import send_email_notification
        round_dates = get_round_date_range(round_number)
        
        for match in matches:
            if match.status == "bye":
                # Notify bye team
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
                        send_email_notification(bye_team.player1_email, f"Round {round_number} - BYE Week", bye_body)
                    if bye_team.player2_email:
                        send_email_notification(bye_team.player2_email, f"Round {round_number} - BYE Week", bye_body)
            else:
                # Notify both teams
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
                        send_email_notification(team_a.player1_email, f"Round {round_number} Pairing - vs {team_b.team_name}", team_a_body)
                    if team_a.player2_email:
                        send_email_notification(team_a.player2_email, f"Round {round_number} Pairing - vs {team_b.team_name}", team_a_body)
                    
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
                        send_email_notification(team_b.player1_email, f"Round {round_number} Pairing - vs {team_a.team_name}", team_b_body)
                    if team_b.player2_email:
                        send_email_notification(team_b.player2_email, f"Round {round_number} Pairing - vs {team_a.team_name}", team_b_body)
            
    except Exception as e:
        flash(f"Error generating round: {str(e)}", "error")
    
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
        total_pending=len(pending_reschedules)
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
                match.match_date = date_str
                match.court = f"Court assignment pending - Rescheduled to {proposed_time}"
            
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
            
            approval_body = f"""Hi!

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

The reschedule request for your match has been APPROVED by admin.

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
    
    try:
        # CRITICAL: If stats were already calculated, reverse them first
        if match.stats_calculated:
            team_a = Team.query.get(match.team_a_id)
            team_b = Team.query.get(match.team_b_id)
            
            if team_a and team_b:
                # Reverse previous stats
                team_a.sets_for -= match.sets_a
                team_a.sets_against -= match.sets_b
                team_a.games_for -= match.games_a
                team_a.games_against -= match.games_b
                
                team_b.sets_for -= match.sets_b
                team_b.sets_against -= match.sets_a
                team_b.games_for -= match.games_b
                team_b.games_against -= match.games_a
                
                # Reverse win/loss/draw/points
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
        flash("Match updated successfully!", "success")
        
    except Exception as e:
        db.session.rollback()
        flash(f"Error updating match: {str(e)}", "error")
    
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

@app.route("/admin/edit-team/<int:team_id>", methods=["GET", "POST"])
@require_admin_auth
def edit_team(team_id):
    team = Team.query.get(team_id)
    if not team:
        flash("Team not found", "error")
        return redirect(url_for("admin_panel"))
    
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
        
        old_player1_phone = team.player1_phone
        old_player2_phone = team.player2_phone
        
        team.team_name = team_name
        team.team_name_canonical = normalize_team_name(team_name)
        team.player1_name = player1_name
        team.player1_email = player1_email if player1_email else None
        team.player1_phone = normalized_phone1
        team.player2_name = player2_name
        team.player2_email = player2_email if player2_email else None
        team.player2_phone = normalized_phone2
        
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
    
    db.session.commit()
    
    # Send confirmation emails to all parties
    from utils import send_email_notification
    
    if match and team:
        subject = f"Substitute Request APPROVED - Round {match.round}"
        
        # Email to Player 1
        if team.player1_email:
            body1 = f"""Hello {team.player1_name},

✅ GOOD NEWS! Your substitute request has been APPROVED by the admin.

Match Details:
- Round: {match.round}
- Team: {team.team_name}
- Substitute: {substitute.name} ({substitute.email})
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
- Match ID: {match.id}

You are now officially approved to play as a substitute for this match. Please coordinate with the team for the match schedule and details.

Thank you for participating!
Padel League Hub"""
            send_email_notification(substitute.email, subject, sub_body)
    
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

Please contact the admin if you have questions or need to submit a different substitute request.

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
            match.status = "completed"
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


@app.route("/rounds")
def rounds():
    matches = Match.query.order_by(Match.round).all()
    rounds_dict = {}
    for match in matches:
        if match.round not in rounds_dict:
            rounds_dict[match.round] = []
        team_a = Team.query.get(match.team_a_id)
        team_b = Team.query.get(match.team_b_id)
        rounds_dict[match.round].append({
            'match': match,
            'team_a': team_a,
            'team_b': team_b
        })
    
    # Get playoff bracket data
    playoff_matches = {}
    quarterfinals = Match.query.filter_by(phase="quarterfinal").order_by(Match.id).all()
    semifinals = Match.query.filter_by(phase="semifinal").order_by(Match.id).all()
    third_place = Match.query.filter_by(phase="third_place").all()
    final = Match.query.filter_by(phase="final").all()
    
    if quarterfinals:
        playoff_matches['quarterfinals'] = []
        for match in quarterfinals:
            playoff_matches['quarterfinals'].append({
                'match': match,
                'team_a': Team.query.get(match.team_a_id),
                'team_b': Team.query.get(match.team_b_id)
            })
    
    if semifinals:
        playoff_matches['semifinals'] = []
        for match in semifinals:
            playoff_matches['semifinals'].append({
                'match': match,
                'team_a': Team.query.get(match.team_a_id),
                'team_b': Team.query.get(match.team_b_id)
            })
    
    if third_place:
        playoff_matches['third_place'] = []
        for match in third_place:
            playoff_matches['third_place'].append({
                'match': match,
                'team_a': Team.query.get(match.team_a_id),
                'team_b': Team.query.get(match.team_b_id)
            })
    
    if final:
        playoff_matches['final'] = []
        for match in final:
            playoff_matches['final'].append({
                'match': match,
                'team_a': Team.query.get(match.team_a_id),
                'team_b': Team.query.get(match.team_b_id)
            })
    
    return render_template("rounds.html", rounds_dict=rounds_dict, playoff_matches=playoff_matches if playoff_matches else None)

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

if __name__ == "__main__":
    # Development mode only
    port = int(os.environ.get("PORT") or 5000)
    debug = os.environ.get("FLASK_ENV") == "development"
    app.run(host="0.0.0.0", port=port, debug=debug)


