import random
import re
import os
from models import Team, Match, db
from sqlalchemy import func

def normalize_team_name(name: str) -> str:
    """Return a canonical form of a team name for duplicate detection.
    - Lowercase
    - Remove all non-alphanumeric characters
    """
    if not name:
        return ""
    # Lowercase and remove non-alphanumeric (including spaces and punctuation)
    lowered = name.lower()
    canonical = re.sub(r"[^a-z0-9]", "", lowered)
    return canonical

def generate_round_pairings(round_number):
    """
    Generates Swiss-format round pairings with detailed logging:
    - Pairs teams with similar standings using exact leaderboard ranking logic
    - Avoids repeat matchups when possible
    - Handles odd number of teams (lowest ranked gets bye)
    - Logs all decision-making for admin transparency
    - Excludes inactive teams from pairing
    - Uses identical ranking to team leaderboard: Status > Points > Sets Diff > Games Diff > Wins > Team Name
    """
    # 1. Get teams sorted by standings (same as public leaderboard)
    # Filter to only active teams, then rank by: Points > Sets Diff > Games Diff > Wins > Team Name
    teams = Team.query.filter_by(status='active').order_by(
        Team.points.desc(),
        (Team.sets_for - Team.sets_against).desc(),
        (Team.games_for - Team.games_against).desc(),
        Team.wins.desc(),
        Team.team_name
    ).all()

    if len(teams) < 2:
        return []

    # Create comprehensive pairing log
    log_lines = []
    log_lines.append(f"=== ROUND {round_number} PAIRING ALGORITHM ===\n")
    log_lines.append(f"Total Teams: {len(teams)}\n")
    log_lines.append("\n--- CURRENT STANDINGS ---")

    for idx, team in enumerate(teams, start=1):
        sets_diff = team.sets_for - team.sets_against
        games_diff = team.games_for - team.games_against
        log_lines.append(
            f"#{idx:2d} | {team.team_name:25s} | Record: {team.wins}-{team.losses}-{team.draws} | "
            f"Points: {team.points:2d} | Sets Diff: {sets_diff:+3d} | Games Diff: {games_diff:+4d}"
        )

    # 2. Build a set of previous matchups to avoid repeats
    previous_matches = Match.query.filter(Match.round < round_number).all()
    already_played = set()
    for match in previous_matches:
        # Store both directions to check either team combination
        already_played.add((min(match.team_a_id, match.team_b_id), 
                          max(match.team_a_id, match.team_b_id)))

    log_lines.append(f"\n--- PREVIOUS MATCHUPS ---")
    log_lines.append(f"Total previous matchups to avoid: {len(already_played)}")

    # 3. Track which teams have been paired
    paired = set()
    matches = []

    log_lines.append(f"\n--- PAIRING DECISIONS ---")

    # 4. Pair teams using Swiss system
    for i, team in enumerate(teams):
        if team.id in paired:
            continue

        # Get team's standing info for logging
        team_rank = i + 1
        team_record = f"{team.wins}-{team.losses}-{team.draws}"

        log_lines.append(f"\n[Pairing #{team_rank}] {team.team_name} ({team_record}, {team.points} pts)")

        # Find best opponent (closest in standings that hasn't played this team)
        opponent = None
        skipped_candidates = []

        for j in range(i + 1, len(teams)):
            candidate = teams[j]
            candidate_rank = j + 1
            candidate_record = f"{candidate.wins}-{candidate.losses}-{candidate.draws}"

            # Skip if already paired
            if candidate.id in paired:
                skipped_candidates.append(
                    f"  ❌ #{candidate_rank} {candidate.team_name} - Already paired in this round"
                )
                continue

            # Check if they've played before
            matchup = (min(team.id, candidate.id), max(team.id, candidate.id))
            if matchup not in already_played:
                opponent = candidate
                
                # Log all skipped candidates before showing the match
                if skipped_candidates:
                    log_lines.append(f"  Skipped candidates:")
                    for skip_msg in skipped_candidates:
                        log_lines.append(skip_msg)
                
                log_lines.append(
                    f"  ✅ Matched with #{candidate_rank} {candidate.team_name} ({candidate_record}, {candidate.points} pts)"
                )
                log_lines.append(f"     Reason: Closest available opponent in standings, no previous matchup")
                break
            else:
                skipped_candidates.append(
                    f"  ⚠️  #{candidate_rank} {candidate.team_name} - Already played in previous round"
                )

        # Log skipped candidates if no opponent found
        if skipped_candidates and not opponent:
            log_lines.append(f"  Candidates considered:")
            for skip_msg in skipped_candidates:
                log_lines.append(skip_msg)

        # If no fresh opponent found, DO NOT pair (skip this team for this round)
        # This ensures we never create repeat matchups, even as a fallback
        if opponent is None:
            log_lines.append(f"  ❌ NO FRESH OPPONENT AVAILABLE - Team cannot be paired this round")
            log_lines.append(f"     Reason: All available teams have already played this team")
            log_lines.append(f"     Action: Team will receive BYE or remain unpaired to preserve Swiss rules")

        # Create the match if we found an opponent
        if opponent:
            pairing_log_text = "\n".join(log_lines)

            match = Match(
                round=round_number,
                team_a_id=team.id,
                team_b_id=opponent.id,
                status="scheduled",
                pairing_log=pairing_log_text
            )
            db.session.add(match)
            matches.append(match)

            # Mark both teams as paired
            paired.add(team.id)
            paired.add(opponent.id)

    # 5. Handle bye (if odd number of teams)
    if len(teams) % 2 == 1:
        # The unpaired team gets a bye (automatically wins)
        bye_team_id = None
        for team in teams:
            if team.id not in paired:
                bye_team_id = team.id
                break

        if bye_team_id:
            bye_team = Team.query.get(bye_team_id)
            bye_rank = teams.index(bye_team) + 1

            log_lines.append(f"\n--- BYE ASSIGNMENT ---")
            log_lines.append(f"#{bye_rank} {bye_team.team_name} receives BYE (odd number of teams)")
            log_lines.append(f"Reason: Lowest-ranked unpaired team in standings")

            pairing_log_text = "\n".join(log_lines)

            match = Match(
                round=round_number,
                team_a_id=bye_team_id,
                team_b_id=None,
                status="bye",
                notes="Bye round - automatic win",
                pairing_log=pairing_log_text
            )
            db.session.add(match)
            matches.append(match)

    log_lines.append(f"\n--- PAIRING COMPLETE ---")
    log_lines.append(f"Total matches created: {len(matches)}")

    db.session.commit()
    return matches


def parse_padel_score(score_str):
    """
    Parse padel score string and return games won.
    Format examples: "6-4, 6-3" or "6-4, 3-6, 10-8" or "6-4 6-3"
    Returns: total games won, or 0 if invalid
    """
    if not score_str:
        return 0

    # Clean and normalize the score string
    score_str = score_str.strip().replace(',', ' ')

    # Match patterns like "6-4" or "10-8"
    pattern = r'(\d+)-(\d+)'
    matches = re.findall(pattern, score_str)

    total_games = 0
    for match in matches:
        games_won = int(match[0])
        total_games += games_won

    return total_games


def calculate_match_result(score_a_str, score_b_str):
    """
    Calculate match result from score strings.
    Returns: (sets_a, sets_b, games_a, games_b, winner_code)
    winner_code: 'a' for team A, 'b' for team B, 'draw' for tie, None for incomplete

    Examples:
    - "6-4, 6-3" vs "4-6, 3-6" = 2-0 sets, team A wins
    - "6-4, 3-6, 10-8" vs "4-6, 6-3, 8-10" = 2-1 sets, team A wins
    """
    if not score_a_str or not score_b_str:
        return 0, 0, 0, 0, None

    # Normalize scores
    score_a_str = score_a_str.strip().replace(',', ' ')
    score_b_str = score_b_str.strip().replace(',', ' ')

    # Extract individual sets
    pattern = r'(\d+)-(\d+)'
    sets_a = re.findall(pattern, score_a_str)
    sets_b = re.findall(pattern, score_b_str)

    if len(sets_a) != len(sets_b):
        # Scores don't match up
        return 0, 0, 0, 0, None

    sets_won_a = 0
    sets_won_b = 0
    games_total_a = 0
    games_total_b = 0

    # Count sets and games
    for i in range(len(sets_a)):
        games_a = int(sets_a[i][0])
        games_b = int(sets_b[i][0])

        games_total_a += games_a
        games_total_b += games_b

        if games_a > games_b:
            sets_won_a += 1
        elif games_b > games_a:
            sets_won_b += 1

    # Determine winner
    winner = None
    if sets_won_a > sets_won_b:
        winner = 'a'
    elif sets_won_b > sets_won_a:
        winner = 'b'
    elif sets_won_a == sets_won_b and sets_won_a > 0:
        winner = 'draw'

    return sets_won_a, sets_won_b, games_total_a, games_total_b, winner


def invert_score_string(score_str: str) -> str:
    """Given a score string for Team A (e.g., "6-4, 3-6, 10-8"),
    produce Team B's perspective ("4-6, 6-3, 8-10").
    """
    if not score_str:
        return ""
    score_str = score_str.strip().replace(',', ' ')
    parts = re.findall(r"(\d+)-(\d+)", score_str)
    swapped = [f"{b}-{a}" for a, b in parts]
    return ", ".join(swapped)


def normalize_score_string(score_str: str) -> str:
    """Normalize a score string into canonical form: "6-4, 3-6, 10-8".
    Ignores commas vs spaces and extra whitespace.
    """
    if not score_str:
        return ""
    score_str = score_str.strip().replace(',', ' ')
    parts = re.findall(r"(\d+)-(\d+)", score_str)
    return ", ".join([f"{a}-{b}" for a, b in parts])


def normalize_phone_number(phone_number):
    """
    Normalize phone number to consistent format for WhatsApp API.
    Removes all non-digit characters and ensures consistent format.
    """
    if not phone_number:
        return None
    # Remove all non-digit characters
    digits = re.sub(r'\D', '', phone_number)
    if not digits:
        return None

    # Strip leading 00 (international prefix sometimes typed)
    if digits.startswith('00'):
        digits = digits[2:]

    default_cc = (os.environ.get('DEFAULT_COUNTRY_CODE') or '').lstrip('+')

    # If number starts with a single leading 0 (local style), prefix default country code
    if default_cc:
        if digits.startswith('0') and len(digits) >= 9:
            digits = default_cc + digits.lstrip('0')
        # If length looks like a local 10/11-digit number and doesn't start with country code, prefix
        elif len(digits) in (9, 10, 11) and not digits.startswith(default_cc):
            digits = default_cc + digits

    return digits


def parse_booking_datetime(booking_text: str) -> tuple[str, object]:
    """
    Parse natural language booking text to extract datetime.
    Returns (datetime_obj, error_message)

    Supported formats:
    - "Saturday 6pm" or "Saturday 18:00"
    - "Next Tuesday 7pm" or "Tuesday 19:00"
    - "Dec 25 6pm" or "December 25 18:00"
    - "25/12 18:00" or "25-12-2024 18:00"
    - "Tomorrow 6pm"
    """
    from datetime import datetime, timedelta
    import re

    booking_text = booking_text.strip().lower()
    now = datetime.now()

    # Try to extract time (e.g., "6pm", "18:00", "6:30pm")
    time_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', booking_text)
    if not time_match:
        return None, "Could not find time in booking. Use format like 'Saturday 6pm' or 'Saturday 18:00'"

    hour = int(time_match.group(1))
    minute = int(time_match.group(2)) if time_match.group(2) else 0
    am_pm = time_match.group(3)

    # Convert to 24-hour format
    if am_pm == 'pm' and hour != 12:
        hour += 12
    elif am_pm == 'am' and hour == 12:
        hour = 0

    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None, "Invalid time. Hour must be 0-23, minute 0-59"

    # Try to extract date
    target_date = None

    # Check for "tomorrow"
    if 'tomorrow' in booking_text:
        target_date = now.date() + timedelta(days=1)

    # Check for day of week
    elif any(day in booking_text for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']):
        days = {'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3, 'friday': 4, 'saturday': 5, 'sunday': 6}
        for day_name, day_num in days.items():
            if day_name in booking_text:
                current_day = now.weekday()
                days_ahead = day_num - current_day
                if days_ahead <= 0:  # Target day is today or in the past
                    days_ahead += 7  # Move to next week
                target_date = now.date() + timedelta(days=days_ahead)
                break

    # Check for DD/MM or DD-MM format
    elif re.search(r'(\d{1,2})[/-](\d{1,2})', booking_text):
        date_match = re.search(r'(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?', booking_text)
        day = int(date_match.group(1))
        month = int(date_match.group(2))
        year = int(date_match.group(3)) if date_match.group(3) else now.year
        if year < 100:  # Two-digit year
            year += 2000
        try:
            target_date = datetime(year, month, day).date()
        except ValueError:
            return None, f"Invalid date: {day}/{month}/{year}"

    # Check for month name
    elif any(month in booking_text for month in ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']):
        months = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6, 
                  'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12}
        for month_name, month_num in months.items():
            if month_name in booking_text:
                day_match = re.search(r'\b(\d{1,2})\b', booking_text)
                if day_match:
                    day = int(day_match.group(1))
                    year = now.year
                    try:
                        target_date = datetime(year, month_num, day).date()
                    except ValueError:
                        return None, f"Invalid date: {day}/{month_num}/{year}"
                break

    if not target_date:
        return None, "Could not find date. Use format like 'Saturday 6pm', 'Tomorrow 7pm', or '25/12 18:00'"

    # Combine date and time
    try:
        match_datetime = datetime.combine(target_date, datetime.min.time().replace(hour=hour, minute=minute))
    except ValueError as e:
        return None, f"Invalid datetime: {e}"

    # Check if datetime is in the past
    if match_datetime < now:
        return None, f"Booking time is in the past: {match_datetime.strftime('%A, %B %d at %I:%M %p')}"

    return match_datetime, None


def verify_match_and_calculate_stats(match, team_a, team_b, db_session):
    """
    Verify a match and calculate all statistics (team + player).
    Centralizes stats calculation to avoid duplication.
    Should be called when both teams confirm the same score.
    """
    from models import Player

    # Update team stats
    if not match.stats_calculated:
        if match.winner_id == team_a.id:
            team_a.wins += 1
            team_a.points += 3
            team_b.losses += 1
        elif match.winner_id == team_b.id:
            team_b.wins += 1
            team_b.points += 3
            team_a.losses += 1
        else:
            team_a.draws += 1
            team_a.points += 1
            team_b.draws += 1
            team_b.points += 1

        team_a.sets_for += match.sets_a
        team_a.sets_against += match.sets_b
        team_a.games_for += match.games_a
        team_a.games_against += match.games_b

        team_b.sets_for += match.sets_b
        team_b.sets_against += match.sets_a
        team_b.games_for += match.games_b
        team_b.games_against += match.games_a

        # Link players to this match (if not already linked)
        if not match.team_a_player1_id:
            player1 = Player.query.filter_by(phone=team_a.player1_phone).first()
            if player1:
                match.team_a_player1_id = player1.id

        if not match.team_a_player2_id:
            player2 = Player.query.filter_by(phone=team_a.player2_phone).first()
            if player2:
                match.team_a_player2_id = player2.id

        if not match.team_b_player1_id:
            player3 = Player.query.filter_by(phone=team_b.player1_phone).first()
            if player3:
                match.team_b_player1_id = player3.id

        if not match.team_b_player2_id:
            player4 = Player.query.filter_by(phone=team_b.player2_phone).first()
            if player4:
                match.team_b_player2_id = player4.id

        # Update individual player stats
        update_player_stats_for_match(match, db_session)

        match.stats_calculated = True


def update_player_stats_for_match(match, db_session):
    """
    Update individual player statistics for a completed match.
    Should be called after a match is verified.
    """
    from models import Player

    # Get the players who participated in this match
    players_team_a = []
    players_team_b = []

    if match.team_a_player1_id:
        players_team_a.append(Player.query.get(match.team_a_player1_id))
    if match.team_a_player2_id:
        players_team_a.append(Player.query.get(match.team_a_player2_id))
    if match.team_b_player1_id:
        players_team_b.append(Player.query.get(match.team_b_player1_id))
    if match.team_b_player2_id:
        players_team_b.append(Player.query.get(match.team_b_player2_id))

    # Update stats for Team A players
    for player in players_team_a:
        if player:
            player.matches_played += 1
            player.sets_for += match.sets_a
            player.sets_against += match.sets_b
            player.games_for += match.games_a
            player.games_against += match.games_b

            if match.winner_id == match.team_a_id:
                player.wins += 1
                player.points += 3
            elif match.winner_id == match.team_b_id:
                player.losses += 1
            else:
                player.draws += 1
                player.points += 1

    # Update stats for Team B players
    for player in players_team_b:
        if player:
            player.matches_played += 1
            player.sets_for += match.sets_b
            player.sets_against += match.sets_a
            player.games_for += match.games_b
            player.games_against += match.games_a

            if match.winner_id == match.team_b_id:
                player.wins += 1
                player.points += 3
            elif match.winner_id == match.team_a_id:
                player.losses += 1
            else:
                player.draws += 1
                player.points += 1


def get_player_by_phone(phone: str):
    """Get or create a Player record by phone number"""
    from models import Player
    from datetime import datetime

    player = Player.query.filter_by(phone=phone).first()
    if not player:
        # Create a new player record
        player = Player(
            name="Unknown",  # Will be updated when they join a team
            phone=phone,
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    return player


def send_email_notification(to_email: str, subject: str, body: str) -> bool:
    """
    Send an email notification.

    Args:
        to_email: Recipient email address
        subject: Email subject
        body: Email body (plain text)

    Returns:
        True if email sent successfully, False otherwise
    """
    import smtplib
    import os
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    # Skip if no email provided
    if not to_email:
        return False

    # Testing mode: redirect all emails to test address
    testing_mode = os.environ.get("TESTING_MODE", "false").lower() == "true"
    original_email = to_email
    if testing_mode:
        to_email = "goeclecticbd@gmail.com"
        print(f"[EMAIL TEST MODE] Redirecting email from {original_email} to {to_email}")

    # Read SMTP configuration from environment
    smtp_server = os.environ.get("SMTP_SERVER")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_username = os.environ.get("SMTP_USERNAME")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    smtp_from = os.environ.get("SMTP_FROM_EMAIL", smtp_username)

    # Skip if SMTP not configured
    if not all([smtp_server, smtp_username, smtp_password]):
        print(f"[EMAIL] SMTP not configured, skipping email to {to_email}")
        return False

    try:
        # Create message
        msg = MIMEMultipart()
        msg['From'] = smtp_from
        msg['To'] = to_email
        msg['Subject'] = subject

        msg.attach(MIMEText(body, 'plain'))

        # Connect and send
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.send_message(msg)

        print(f"[EMAIL] Successfully sent to {to_email}: {subject}")
        return True

    except Exception as e:
        print(f"[EMAIL ERROR] Failed to send to {to_email}: {e}")
        return False


# ============================================================================
# PLAYOFF GENERATION FUNCTIONS
# ============================================================================

def check_swiss_completion():
    """
    Check if all Swiss rounds are complete.
    Returns: (bool: complete, int: completed_rounds, int: total_swiss_rounds)
    """
    from models import LeagueSettings

    settings = LeagueSettings.query.first()
    if not settings:
        return (False, 0, 5)

    # Count how many rounds have ALL matches completed
    completed_rounds = 0
    for round_num in range(1, settings.swiss_rounds_count + 1):
        round_matches = Match.query.filter_by(round=round_num, phase="swiss").all()
        if not round_matches:
            break

        # Check if all matches in this round are completed or bye
        all_complete = all(m.status in ("completed", "bye") for m in round_matches)
        if all_complete:
            completed_rounds += 1
        else:
            break

    swiss_complete = (completed_rounds >= settings.swiss_rounds_count)
    return (swiss_complete, completed_rounds, settings.swiss_rounds_count)


def get_team_rankings_with_tiebreaker():
    """
    Rank all teams with complete tiebreaker logic:
    1. Points (descending)
    2. Sets differential (descending)
    3. Games differential (descending)
    4. Head-to-head record (if 2 teams tied on all above)
    5. Team ID (registration order)

    Returns: List of (team, rank) tuples sorted by ranking
    """
    from models import Team

    # Get all confirmed teams
    teams = Team.query.filter_by(confirmed=True).all()

    # Sort teams by: points desc, sets_diff desc, games_diff desc, id asc
    teams_sorted = sorted(
        teams,
        key=lambda t: (
            -t.points,
            -(t.sets_for - t.sets_against),
            -(t.games_for - t.games_against),
            t.id
        )
    )

    # Add rank numbers
    ranked_teams = []
    for idx, team in enumerate(teams_sorted, start=1):
        ranked_teams.append((team, idx))

    return ranked_teams


def get_head_to_head_winner(team_a_id, team_b_id):
    """
    Check head-to-head record between two teams.
    Returns: winning team_id or None if they haven't played or it's a draw
    """
    # Find match between these two teams (Swiss rounds only)
    match = Match.query.filter(
        Match.phase == "swiss",
        Match.status == "completed",
        db.or_(
            db.and_(Match.team_a_id == team_a_id, Match.team_b_id == team_b_id),
            db.and_(Match.team_a_id == team_b_id, Match.team_b_id == team_a_id)
        )
    ).first()

    if match and match.winner_id:
        return match.winner_id
    return None


def generate_playoff_preview():
    """
    Generate playoff preview data showing Top 8 teams and their seeding.
    Returns: dict with preview data for admin approval
    """
    from models import LeagueSettings

    settings = LeagueSettings.query.first()
    if not settings:
        return None

    # Get ranked teams
    ranked_teams = get_team_rankings_with_tiebreaker()

    # Get top 8 teams for playoffs
    top_8 = ranked_teams[:8] if len(ranked_teams) >= 8 else ranked_teams[:4]

    # Build preview data
    preview = {
        'qualified_teams': [],
        'bracket_preview': [],
        'settings': settings
    }

    for team, rank in top_8:
        preview['qualified_teams'].append({
            'team': team,
            'seed': rank,
            'points': team.points,
            'sets_diff': team.sets_diff,
            'games_diff': team.games_diff
        })

    # Generate bracket preview (matchups)
    if len(top_8) >= 8:
        preview['bracket_preview'] = [
            {'match': 'QF1', 'seed1': 1, 'seed8': 8, 'team1': top_8[0][0].team_name, 'team8': top_8[7][0].team_name},
            {'match': 'QF2', 'seed2': 2, 'seed7': 7, 'team2': top_8[1][0].team_name, 'team7': top_8[6][0].team_name},
            {'match': 'QF3', 'seed3': 3, 'seed6': 6, 'team3': top_8[2][0].team_name, 'team6': top_8[5][0].team_name},
            {'match': 'QF4', 'seed4': 4, 'seed5': 5, 'team4': top_8[3][0].team_name, 'team5': top_8[4][0].team_name},
        ]
    elif len(top_8) >= 4:
        preview['bracket_preview'] = [
            {'match': 'SF1', 'seed1': 1, 'seed4': 4, 'team1': top_8[0][0].team_name, 'team4': top_8[3][0].team_name},
            {'match': 'SF2', 'seed2': 2, 'seed3': 3, 'team2': top_8[1][0].team_name, 'team3': top_8[2][0].team_name},
        ]

    return preview


def generate_playoff_bracket(round_number, phase_type):
    """
    Generate playoff matches based on phase:

    - "quarterfinal": Top 8 teams, seeded 1v8, 2v7, 3v6, 4v5
    - "semifinal": Winners from quarters (or Top 4 if no quarters)
    - "third_place": Losers from semi-finals
    - "final": Winners from semi-finals

    Creates Match records with phase field set appropriately.
    Returns: List of created matches
    """
    from models import LeagueSettings
    import json

    settings = LeagueSettings.query.first()
    if not settings:
        return []

    matches_created = []

    if phase_type == "quarterfinal":
        # Get qualified team IDs from settings
        if settings.qualified_team_ids:
            team_ids = json.loads(settings.qualified_team_ids)
        else:
            # Fallback: get top 8 from rankings
            ranked_teams = get_team_rankings_with_tiebreaker()
            team_ids = [t[0].id for t in ranked_teams[:8]]

        if len(team_ids) < 8:
            return []

        # Create quarterfinal matches (1v8, 2v7, 3v6, 4v5)
        matchups = [
            (team_ids[0], team_ids[7], "QF1: Seed 1 vs Seed 8"),
            (team_ids[1], team_ids[6], "QF2: Seed 2 vs Seed 7"),
            (team_ids[2], team_ids[5], "QF3: Seed 3 vs Seed 6"),
            (team_ids[3], team_ids[4], "QF4: Seed 4 vs Seed 5"),
        ]

        for team_a_id, team_b_id, notes in matchups:
            match = Match(
                round=round_number,
                phase="quarterfinal",
                team_a_id=team_a_id,
                team_b_id=team_b_id,
                status="scheduled",
                notes=notes
            )
            db.session.add(match)
            matches_created.append(match)

    elif phase_type == "semifinal":
        # Check if there were quarterfinals
        quarters = Match.query.filter_by(phase="quarterfinal").all()

        if quarters and len(quarters) == 4:
            # Get winners from quarters
            qf_winners = []
            for qf in sorted(quarters, key=lambda m: m.id):
                if qf.winner_id:
                    qf_winners.append(qf.winner_id)

            if len(qf_winners) == 4:
                # SF1: QF1 winner vs QF2 winner
                # SF2: QF3 winner vs QF4 winner
                matchups = [
                    (qf_winners[0], qf_winners[1], "SF1: QF1 Winner vs QF2 Winner"),
                    (qf_winners[2], qf_winners[3], "SF2: QF3 Winner vs QF4 Winner"),
                ]

                for team_a_id, team_b_id, notes in matchups:
                    match = Match(
                        round=round_number,
                        phase="semifinal",
                        team_a_id=team_a_id,
                        team_b_id=team_b_id,
                        status="scheduled",
                        notes=notes
                    )
                    db.session.add(match)
                    matches_created.append(match)
        else:
            # No quarters, use Top 4 directly
            if settings.qualified_team_ids:
                team_ids = json.loads(settings.qualified_team_ids)[:4]
            else:
                ranked_teams = get_team_rankings_with_tiebreaker()
                team_ids = [t[0].id for t in ranked_teams[:4]]

            if len(team_ids) >= 4:
                matchups = [
                    (team_ids[0], team_ids[3], "SF1: Seed 1 vs Seed 4"),
                    (team_ids[1], team_ids[2], "SF2: Seed 2 vs Seed 3"),
                ]

                for team_a_id, team_b_id, notes in matchups:
                    match = Match(
                        round=round_number,
                        phase="semifinal",
                        team_a_id=team_a_id,
                        team_b_id=team_b_id,
                        status="scheduled",
                        notes=notes
                    )
                    db.session.add(match)
                    matches_created.append(match)

    elif phase_type == "third_place":
        # Get losers from semifinals
        semis = Match.query.filter_by(phase="semifinal").all()
        sf_losers = []

        for sf in semis:
            if sf.winner_id and sf.team_a_id and sf.team_b_id:
                loser_id = sf.team_b_id if sf.winner_id == sf.team_a_id else sf.team_a_id
                sf_losers.append(loser_id)

        if len(sf_losers) == 2:
            match = Match(
                round=round_number,
                phase="third_place",
                team_a_id=sf_losers[0],
                team_b_id=sf_losers[1],
                status="scheduled",
                notes="3rd Place Match"
            )
            db.session.add(match)
            matches_created.append(match)

    elif phase_type == "final":
        # Get winners from semifinals
        semis = Match.query.filter_by(phase="semifinal").all()
        sf_winners = []

        for sf in semis:
            if sf.winner_id:
                sf_winners.append(sf.winner_id)

        if len(sf_winners) == 2:
            match = Match(
                round=round_number,
                phase="final",
                team_a_id=sf_winners[0],
                team_b_id=sf_winners[1],
                status="scheduled",
                notes="FINAL"
            )
            db.session.add(match)
            matches_created.append(match)

    db.session.commit()
    return matches_created


def get_playoff_bracket_data():
    """
    Return structured playoff bracket data for template rendering:
    {
        'quarterfinals': [match objects],
        'semifinals': [match objects],
        'third_place': match object,
        'final': match object
    }
    """
    bracket_data = {
        'quarterfinals': Match.query.filter_by(phase="quarterfinal").order_by(Match.id).all(),
        'semifinals': Match.query.filter_by(phase="semifinal").order_by(Match.id).all(),
        'third_place': Match.query.filter_by(phase="third_place").first(),
        'final': Match.query.filter_by(phase="final").first()
    }

    return bracket_data


# Function to get pending reschedules - assumed to exist elsewhere or needs definition
def get_pending_reschedules():
    """
    Placeholder function to get pending reschedules.
    Replace with actual implementation if not available.
    """
    # Example implementation:
    # from models import RescheduleRequest
    # return RescheduleRequest.query.filter_by(status='pending').all()
    return []

def check_reschedule_conflicts(proposed_matches):
    """Check if proposed matches conflict with pending reschedules"""
    from models import Match
    pending_reschedules = get_pending_reschedules()
    conflicts = []

    for match in proposed_matches:
        # Handle Match objects (not dicts)
        team_a_id = match.team_a_id
        team_b_id = match.team_b_id

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


# ============================================================================
# LADDER UTILITY FUNCTIONS
# ============================================================================

def swap_ladder_ranks(winner_team, loser_team, ladder_type):
    """
    Swap ladder ranks between winner and loser after a match.
    - If winner has lower rank (higher number), they take the loser's rank
    - All teams between them shift down one rank
    - Returns dict with old and new ranks for logging
    
    Args:
        winner_team: LadderTeam object (winner)
        loser_team: LadderTeam object (loser)
        ladder_type: 'men' or 'women'
    
    Returns:
        dict with rank changes: {'winner': {'old': X, 'new': Y}, 'loser': {...}, 'affected_teams': [...]}
    """
    from models import LadderTeam
    
    # Don't swap if winner is already higher ranked (lower number)
    if winner_team.current_rank <= loser_team.current_rank:
        return {
            'winner': {'old': winner_team.current_rank, 'new': winner_team.current_rank},
            'loser': {'old': loser_team.current_rank, 'new': loser_team.current_rank},
            'affected_teams': [],
            'message': 'No rank change - winner already higher ranked'
        }
    
    # Check if either team is in holiday mode - don't swap ranks
    if winner_team.holiday_mode_active or loser_team.holiday_mode_active:
        return {
            'winner': {'old': winner_team.current_rank, 'new': winner_team.current_rank},
            'loser': {'old': loser_team.current_rank, 'new': loser_team.current_rank},
            'affected_teams': [],
            'message': 'No rank change - team in holiday mode'
        }
    
    winner_old_rank = winner_team.current_rank
    loser_old_rank = loser_team.current_rank
    
    # Winner takes loser's rank
    winner_new_rank = loser_old_rank
    
    # Get all teams between winner and loser (exclusive)
    teams_to_shift = LadderTeam.query.filter(
        LadderTeam.ladder_type == ladder_type,
        LadderTeam.current_rank >= winner_new_rank,
        LadderTeam.current_rank < winner_old_rank
    ).all()
    
    affected_teams = []
    
    # Shift all teams between them down one rank
    for team in teams_to_shift:
        old_rank = team.current_rank
        team.current_rank += 1
        affected_teams.append({
            'team_name': team.team_name,
            'old_rank': old_rank,
            'new_rank': team.current_rank
        })
    
    # Set new ranks
    winner_team.current_rank = winner_new_rank
    loser_team.current_rank = loser_old_rank + 1  # Loser shifts down by 1
    
    db.session.commit()
    
    return {
        'winner': {'old': winner_old_rank, 'new': winner_new_rank},
        'loser': {'old': loser_old_rank, 'new': loser_team.current_rank},
        'affected_teams': affected_teams,
        'message': f'Ranks swapped successfully'
    }


def apply_rank_penalty(team, penalty_ranks, reason, ladder_type):
    """
    Apply rank penalty to a team (move them down the ladder).
    - Shifts team down by penalty_ranks positions
    - Adjusts all teams between old and new positions
    - Sends email notification to team
    
    Args:
        team: LadderTeam object
        penalty_ranks: Number of ranks to penalize (positive integer)
        reason: String explaining why penalty was applied
        ladder_type: 'men' or 'women'
    
    Returns:
        dict with rank change info
    """
    from models import LadderTeam
    from datetime import datetime
    
    if penalty_ranks <= 0:
        return {
            'team': team.team_name,
            'old_rank': team.current_rank,
            'new_rank': team.current_rank,
            'message': 'No penalty applied - penalty_ranks must be positive'
        }
    
    old_rank = team.current_rank
    new_rank = old_rank + penalty_ranks
    
    # Get max rank in ladder to ensure we don't exceed it
    max_rank_team = LadderTeam.query.filter_by(ladder_type=ladder_type).order_by(
        LadderTeam.current_rank.desc()
    ).first()
    
    if max_rank_team:
        max_rank = max_rank_team.current_rank
        if new_rank > max_rank:
            new_rank = max_rank
    
    # Get all teams between old and new rank (move them up)
    teams_to_shift = LadderTeam.query.filter(
        LadderTeam.ladder_type == ladder_type,
        LadderTeam.current_rank > old_rank,
        LadderTeam.current_rank <= new_rank
    ).all()
    
    affected_teams = []
    
    # Shift teams up by 1 rank
    for t in teams_to_shift:
        old_r = t.current_rank
        t.current_rank -= 1
        affected_teams.append({
            'team_name': t.team_name,
            'old_rank': old_r,
            'new_rank': t.current_rank
        })
    
    # Apply penalty to team
    team.current_rank = new_rank
    
    db.session.commit()
    
    # Send email notification
    penalty_email_body = f"""Hi {team.player1_name},

RANK PENALTY APPLIED

Your team "{team.team_name}" has received a rank penalty on the {ladder_type.title()} Ladder.

Penalty Details:
- Reason: {reason}
- Old Rank: #{old_rank}
- New Rank: #{new_rank}
- Penalty: {penalty_ranks} rank(s)
- Date: {datetime.now().strftime('%B %d, %Y')}

If you believe this penalty was applied in error, please contact the admin immediately.

- BD Padel League
"""
    
    if team.player1_email:
        send_email_notification(team.player1_email, "Rank Penalty Applied", penalty_email_body)
    if team.player2_email:
        send_email_notification(team.player2_email, "Rank Penalty Applied", penalty_email_body)
    
    return {
        'team': team.team_name,
        'old_rank': old_rank,
        'new_rank': new_rank,
        'affected_teams': affected_teams,
        'message': f'Penalty of {penalty_ranks} rank(s) applied successfully'
    }


def update_ladder_team_stats(match, winner_team, loser_team):
    """
    Update team statistics after a ladder match is completed.
    
    Args:
        match: LadderMatch object
        winner_team: LadderTeam object (winner)
        loser_team: LadderTeam object (loser)
    """
    from datetime import datetime
    
    # Update winner stats
    winner_team.wins += 1
    winner_team.sets_for += match.sets_a if match.winner_id == match.team_a_id else match.sets_b
    winner_team.sets_against += match.sets_b if match.winner_id == match.team_a_id else match.sets_a
    winner_team.games_for += match.games_a if match.winner_id == match.team_a_id else match.games_b
    winner_team.games_against += match.games_b if match.winner_id == match.team_a_id else match.games_a
    winner_team.last_match_date = datetime.now()
    winner_team.matches_this_month = (winner_team.matches_this_month or 0) + 1
    
    # Update loser stats
    loser_team.losses += 1
    loser_team.sets_for += match.sets_b if match.winner_id == match.team_a_id else match.sets_a
    loser_team.sets_against += match.sets_a if match.winner_id == match.team_a_id else match.sets_b
    loser_team.games_for += match.games_b if match.winner_id == match.team_a_id else match.games_a
    loser_team.games_against += match.games_a if match.winner_id == match.team_a_id else match.games_b
    loser_team.last_match_date = datetime.now()
    loser_team.matches_this_month = (loser_team.matches_this_month or 0) + 1
    
    # Mark stats as calculated
    match.stats_calculated = True
    
    db.session.commit()


def adjust_ladder_ranks(team, new_rank, ladder_type):
    """
    Admin function to manually adjust a team's rank on the ladder.
    Similar to apply_rank_penalty but handles both moving up and down.
    
    Args:
        team: LadderTeam object to adjust
        new_rank: Target rank (1-indexed)
        ladder_type: 'men' or 'women'
    
    Returns:
        dict with adjustment details and affected teams
    """
    from models import LadderTeam
    from datetime import datetime
    
    old_rank = team.current_rank
    
    if new_rank == old_rank:
        return {
            'success': False,
            'message': 'Team is already at rank #{}'.format(new_rank)
        }
    
    # Validate new_rank is within bounds
    max_rank_team = LadderTeam.query.filter_by(ladder_type=ladder_type).order_by(
        LadderTeam.current_rank.desc()
    ).first()
    
    if max_rank_team:
        max_rank = max_rank_team.current_rank
        if new_rank < 1 or new_rank > max_rank:
            return {
                'success': False,
                'message': 'New rank must be between 1 and {}'.format(max_rank)
            }
    
    affected_teams = []
    
    if new_rank < old_rank:
        # Moving up (lower rank number) - teams between new_rank and old_rank move down
        teams_to_shift = LadderTeam.query.filter(
            LadderTeam.ladder_type == ladder_type,
            LadderTeam.current_rank >= new_rank,
            LadderTeam.current_rank < old_rank
        ).all()
        
        # Shift teams down by 1 rank
        for t in teams_to_shift:
            old_r = t.current_rank
            t.current_rank += 1
            affected_teams.append({
                'team_id': t.id,
                'team_name': t.team_name,
                'old_rank': old_r,
                'new_rank': t.current_rank
            })
    
    else:
        # Moving down (higher rank number) - teams between old_rank and new_rank move up
        teams_to_shift = LadderTeam.query.filter(
            LadderTeam.ladder_type == ladder_type,
            LadderTeam.current_rank > old_rank,
            LadderTeam.current_rank <= new_rank
        ).all()
        
        # Shift teams up by 1 rank
        for t in teams_to_shift:
            old_r = t.current_rank
            t.current_rank -= 1
            affected_teams.append({
                'team_id': t.id,
                'team_name': t.team_name,
                'old_rank': old_r,
                'new_rank': t.current_rank
            })
    
    # Apply the new rank to the target team
    team.current_rank = new_rank
    team.updated_at = datetime.now()
    
    db.session.commit()
    
    return {
        'success': True,
        'team': team.team_name,
        'old_rank': old_rank,
        'new_rank': new_rank,
        'affected_teams': affected_teams,
        'message': 'Rank adjusted from #{} to #{}'.format(old_rank, new_rank)
    }


def generate_americano_pairings(player_ids):
    """
    Generate Americano tournament pairings where:
    - Each player plays multiple rounds
    - Partners rotate each round
    - Opponents change each round
    - Maximum variety in matchups
    
    Args:
        player_ids: List of player IDs (LadderFreeAgent IDs)
    
    Returns:
        List of rounds, where each round contains matches
        Each match is a tuple: (player1_id, player2_id, player3_id, player4_id)
        Team A = player1 + player2, Team B = player3 + player4
    
    Algorithm for 8 players (standard Americano):
    - 7 rounds total
    - Each round has 4 players (2v2)
    - Each player sits out once (when n is divisible by 4, no one sits)
    - Maximizes partner and opponent variety
    """
    import itertools
    from collections import defaultdict
    
    num_players = len(player_ids)
    
    if num_players < 4:
        return []
    
    # Track partnerships and oppositions to maximize variety
    partnerships = defaultdict(int)
    oppositions = defaultdict(int)
    
    def get_partnership_key(p1, p2):
        return tuple(sorted([p1, p2]))
    
    def get_opposition_key(p1, p2, p3, p4):
        team_a = tuple(sorted([p1, p2]))
        team_b = tuple(sorted([p3, p4]))
        return (team_a, team_b) if team_a < team_b else (team_b, team_a)
    
    # Calculate number of rounds (each player plays n-1 rounds if even, n rounds if odd)
    if num_players % 2 == 0:
        num_rounds = num_players - 1
    else:
        num_rounds = num_players
    
    rounds = []
    player_list = player_ids.copy()
    
    # Use round-robin tournament algorithm (for doubles)
    # For 8 players: rounds 1-7, each player plays 7 matches
    
    for round_num in range(num_rounds):
        round_matches = []
        players_in_round = []
        
        # For round-robin, we rotate players but keep one fixed
        if round_num == 0:
            # Initial setup
            players_in_round = player_list.copy()
        else:
            # Rotate all players except the first one
            fixed = player_list[0]
            rotating = player_list[1:]
            # Rotate right
            rotating = [rotating[-1]] + rotating[:-1]
            players_in_round = [fixed] + rotating
            player_list = players_in_round.copy()
        
        # Create matches for this round
        # Pair players: (0,1) vs (2,3), (4,5) vs (6,7), etc.
        num_matches = num_players // 4
        
        for i in range(num_matches):
            idx_start = i * 4
            if idx_start + 3 < len(players_in_round):
                p1 = players_in_round[idx_start]
                p2 = players_in_round[idx_start + 1]
                p3 = players_in_round[idx_start + 2]
                p4 = players_in_round[idx_start + 3]
                
                match = (p1, p2, p3, p4)
                round_matches.append(match)
                
                # Track partnerships and oppositions
                partnerships[get_partnership_key(p1, p2)] += 1
                partnerships[get_partnership_key(p3, p4)] += 1
                oppositions[get_opposition_key(p1, p2, p3, p4)] += 1
        
        rounds.append(round_matches)
    
    return rounds