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
    Generates Swiss-format round pairings:
    - Pairs teams with similar standings (wins, then sets differential)
    - Avoids repeat matchups when possible
    - Handles odd number of teams (lowest ranked gets bye)
    """
    # 1. Get teams sorted by standings (wins desc, then sets differential desc)
    teams = Team.query.order_by(
        Team.wins.desc(),
        (Team.sets_for - Team.sets_against).desc(),
        Team.id
    ).all()
    
    if len(teams) < 2:
        return []
    
    # 2. Build a set of previous matchups to avoid repeats
    previous_matches = Match.query.filter(Match.round < round_number).all()
    already_played = set()
    for match in previous_matches:
        # Store both directions to check either team combination
        already_played.add((min(match.team_a_id, match.team_b_id), 
                          max(match.team_a_id, match.team_b_id)))
    
    # 3. Track which teams have been paired
    paired = set()
    matches = []
    
    # 4. Pair teams using Swiss system
    for i, team in enumerate(teams):
        if team.id in paired:
            continue
            
        # Find best opponent (closest in standings that hasn't played this team)
        opponent = None
        for j in range(i + 1, len(teams)):
            candidate = teams[j]
            
            # Skip if already paired
            if candidate.id in paired:
                continue
            
            # Check if they've played before
            matchup = (min(team.id, candidate.id), max(team.id, candidate.id))
            if matchup not in already_played:
                opponent = candidate
                break
        
        # If no fresh opponent found, pair with anyone available (fallback)
        if opponent is None:
            for j in range(i + 1, len(teams)):
                candidate = teams[j]
                if candidate.id not in paired:
                    opponent = candidate
                    break
        
        # Create the match if we found an opponent
        if opponent:
            match = Match(
                round=round_number,
                team_a_id=team.id,
                team_b_id=opponent.id,
                status="scheduled"
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
            # Record bye as a win (optional - you can customize this)
            # For now, just create a match record with status "bye"
            match = Match(
                round=round_number,
                team_a_id=bye_team_id,
                team_b_id=None,
                status="bye",
                notes="Bye round - automatic win"
            )
            db.session.add(match)
            matches.append(match)
    
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


