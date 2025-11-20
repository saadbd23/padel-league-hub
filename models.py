from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_name = db.Column(db.String(100), nullable=False)
    team_name_canonical = db.Column(db.String(120), index=True)
    player1_name = db.Column(db.String(100))
    player1_phone = db.Column(db.String(20))
    player1_email = db.Column(db.String(120))  # Optional, for email notifications
    player2_name = db.Column(db.String(100))
    player2_phone = db.Column(db.String(20))
    player2_email = db.Column(db.String(120))  # Optional, for email notifications
    confirmed = db.Column(db.Boolean, default=False)  # Admin can override
    player2_confirmed = db.Column(db.Boolean, default=False)  # Player 2's confirmation status
    player2_confirmation_token = db.Column(db.String(64), unique=True, index=True)  # Token for Player 2 to confirm
    subs_used = db.Column(db.Integer, default=0)
    reschedules_used = db.Column(db.Integer, default=0)
    access_token = db.Column(db.String(64), unique=True, index=True)  # Unique token for secure access

    # Match statistics
    wins = db.Column(db.Integer, default=0)
    losses = db.Column(db.Integer, default=0)
    draws = db.Column(db.Integer, default=0)
    points = db.Column(db.Integer, default=0)  # 3 for win, 1 for draw, 0 for loss

    # Set statistics
    sets_for = db.Column(db.Integer, default=0)
    sets_against = db.Column(db.Integer, default=0)

    # Game statistics (within sets)
    games_for = db.Column(db.Integer, default=0)
    games_against = db.Column(db.Integer, default=0)

    @property
    def sets_diff(self):
        return self.sets_for - self.sets_against

    @property
    def games_diff(self):
        return self.games_for - self.games_against

    @property
    def matches_played(self):
        return self.wins + self.losses + self.draws

class Player(db.Model):
    """Individual player with their own statistics across all matches they've played"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), unique=True, index=True)  # Unique identifier
    email = db.Column(db.String(120))

    # Match statistics (accumulated from all matches they've played)
    matches_played = db.Column(db.Integer, default=0)
    wins = db.Column(db.Integer, default=0)
    losses = db.Column(db.Integer, default=0)
    draws = db.Column(db.Integer, default=0)
    points = db.Column(db.Integer, default=0)  # 3 for win, 1 for draw, 0 for loss

    # Set statistics
    sets_for = db.Column(db.Integer, default=0)
    sets_against = db.Column(db.Integer, default=0)

    # Game statistics
    games_for = db.Column(db.Integer, default=0)
    games_against = db.Column(db.Integer, default=0)

    # Metadata
    current_team_id = db.Column(db.Integer, nullable=True)  # Current team (if any)
    created_at = db.Column(db.String(50))

    @property
    def win_percentage(self):
        if self.matches_played == 0:
            return 0.0
        return round((self.wins / self.matches_played) * 100, 1)

    @property
    def sets_diff(self):
        return self.sets_for - self.sets_against

    @property
    def games_diff(self):
        return self.games_for - self.games_against

class FreeAgent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120))
    skill_level = db.Column(db.String(20))
    playstyle = db.Column(db.String(50))
    availability = db.Column(db.String(100))
    paired = db.Column(db.Boolean, default=False)
    partner_id = db.Column(db.Integer, nullable=True)

class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    round = db.Column(db.Integer)
    phase = db.Column(db.String(20), default="swiss")  # swiss, quarterfinal, semifinal, third_place, final
    team_a_id = db.Column(db.Integer)
    team_b_id = db.Column(db.Integer, nullable=True)  # Nullable for bye rounds

    # Scores (format: "6-4, 6-3" or "6-4, 3-6, 10-8")
    score_a = db.Column(db.String(50))
    score_b = db.Column(db.String(50))

    # Match result
    winner_id = db.Column(db.Integer, nullable=True)
    sets_a = db.Column(db.Integer, default=0)
    sets_b = db.Column(db.Integer, default=0)
    games_a = db.Column(db.Integer, default=0)
    games_b = db.Column(db.Integer, default=0)

    # Match metadata
    match_date = db.Column(db.String(50))  # Store as string for now
    match_datetime = db.Column(db.DateTime, nullable=True)  # Parsed datetime for reminders
    court = db.Column(db.String(50))
    verified = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), default="scheduled")  # scheduled, completed, bye, walkover
    stats_calculated = db.Column(db.Boolean, default=False)  # Prevent duplicate updates
    notes = db.Column(db.String(200))
    booking_details = db.Column(db.Text)  # Store court booking info from teams
    booking_confirmed = db.Column(db.Boolean, default=False)  # Both teams confirmed booking
    reminder_sent = db.Column(db.Boolean, default=False)  # 24h reminder sent flag
    pairing_log = db.Column(db.Text, nullable=True)  # Swiss pairing algorithm decision log

    # Score submission tracking (two-team confirmation)
    score_submission_a = db.Column(db.Text)  # Team A's submitted score
    score_submission_b = db.Column(db.Text)  # Team B's submitted score
    score_submitted_by_a = db.Column(db.Boolean, default=False)  # Team A submitted
    score_submitted_by_b = db.Column(db.Boolean, default=False)  # Team B submitted

    # Player participation tracking (for individual stats)
    # Stores player IDs who actually played in this match
    team_a_player1_id = db.Column(db.Integer, nullable=True)  # Team A player 1
    team_a_player2_id = db.Column(db.Integer, nullable=True)  # Team A player 2
    team_b_player1_id = db.Column(db.Integer, nullable=True)  # Team B player 1
    team_b_player2_id = db.Column(db.Integer, nullable=True)  # Team B player 2


class Reschedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer)
    requester_team_id = db.Column(db.Integer)
    proposed_time = db.Column(db.String(100))
    status = db.Column(db.String(20), default="pending")  # pending/approved/denied
    approved_by_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.String(50))


class Substitute(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer)
    match_id = db.Column(db.Integer)
    name = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100), nullable=True)  # Substitute's email address
    player_id = db.Column(db.Integer, nullable=True)  # Links to Player model
    replaces_player_number = db.Column(db.Integer, nullable=True)  # 1 or 2 (which team player they're replacing)
    status = db.Column(db.String(20), default="pending")  # pending/approved/denied
    created_at = db.Column(db.String(50))


class LeagueSettings(db.Model):
    __tablename__ = 'league_settings'

    id = db.Column(db.Integer, primary_key=True)
    swiss_rounds_count = db.Column(db.Integer, default=5)
    playoff_teams_count = db.Column(db.Integer, default=8)
    current_phase = db.Column(db.String(50), default="swiss")
    playoffs_approved = db.Column(db.Boolean, default=False)
    qualified_team_ids = db.Column(db.Text, nullable=True)
    team_registration_open = db.Column(db.Boolean, default=True)
    freeagent_registration_open = db.Column(db.Boolean, default=True)


class LadderTeam(db.Model):
    __tablename__ = 'ladder_team'
    
    id = db.Column(db.Integer, primary_key=True)
    team_name = db.Column(db.String(100), nullable=False)
    team_name_canonical = db.Column(db.String(120), index=True)
    player1_name = db.Column(db.String(100))
    player1_phone = db.Column(db.String(20))
    player1_email = db.Column(db.String(120))
    player2_name = db.Column(db.String(100))
    player2_phone = db.Column(db.String(20))
    player2_email = db.Column(db.String(120))
    
    gender = db.Column(db.String(10), nullable=False)  # 'men', 'women', or 'mixed'
    ladder_type = db.Column(db.String(10), nullable=False)  # 'men', 'women', or 'mixed'
    current_rank = db.Column(db.Integer, nullable=False)
    
    # Mixed ladder specific fields
    player1_gender = db.Column(db.String(10), nullable=True)  # 'male' or 'female' for mixed teams
    player2_gender = db.Column(db.String(10), nullable=True)  # 'male' or 'female' for mixed teams
    
    contact_preference_email = db.Column(db.Boolean, default=True)
    contact_preference_whatsapp = db.Column(db.Boolean, default=False)
    access_token = db.Column(db.String(64), unique=True, index=True)
    
    wins = db.Column(db.Integer, default=0)
    losses = db.Column(db.Integer, default=0)
    draws = db.Column(db.Integer, default=0)
    
    sets_for = db.Column(db.Integer, default=0)
    sets_against = db.Column(db.Integer, default=0)
    games_for = db.Column(db.Integer, default=0)
    games_against = db.Column(db.Integer, default=0)
    
    last_match_date = db.Column(db.DateTime, nullable=True)
    matches_this_month = db.Column(db.Integer, default=0)
    
    holiday_mode_active = db.Column(db.Boolean, default=False)
    holiday_mode_start = db.Column(db.DateTime, nullable=True)
    holiday_mode_end = db.Column(db.DateTime, nullable=True)
    
    payment_received = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=True)
    
    @property
    def sets_diff(self):
        return self.sets_for - self.sets_against
    
    @property
    def games_diff(self):
        return self.games_for - self.games_against
    
    @property
    def matches_played(self):
        return self.wins + self.losses + self.draws


class LadderFreeAgent(db.Model):
    __tablename__ = 'ladder_free_agent'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    gender = db.Column(db.String(10), nullable=False)
    
    contact_preference_email = db.Column(db.Boolean, default=True)
    contact_preference_whatsapp = db.Column(db.Boolean, default=False)
    access_token = db.Column(db.String(64), unique=True, index=True)
    
    skill_level = db.Column(db.String(20), nullable=True)
    playstyle = db.Column(db.String(50), nullable=True)
    availability = db.Column(db.String(100), nullable=True)
    
    partner_requested = db.Column(db.Boolean, default=False)
    partner_request_deadline = db.Column(db.DateTime, nullable=True)
    
    created_at = db.Column(db.DateTime, nullable=True)


class LadderChallenge(db.Model):
    __tablename__ = 'ladder_challenge'
    
    id = db.Column(db.Integer, primary_key=True)
    challenger_team_id = db.Column(db.Integer, nullable=False)
    challenged_team_id = db.Column(db.Integer, nullable=False)
    ladder_type = db.Column(db.String(10), nullable=False)
    
    status = db.Column(db.String(30), default="pending_acceptance")
    acceptance_deadline = db.Column(db.DateTime, nullable=False)
    completion_deadline = db.Column(db.DateTime, nullable=True)
    
    no_show_reported_by = db.Column(db.Integer, nullable=True)
    no_show_dispute = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, nullable=True)
    accepted_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)


class LadderMatch(db.Model):
    __tablename__ = 'ladder_match'
    
    id = db.Column(db.Integer, primary_key=True)
    challenge_id = db.Column(db.Integer, nullable=False)
    team_a_id = db.Column(db.Integer, nullable=False)
    team_b_id = db.Column(db.Integer, nullable=False)
    ladder_type = db.Column(db.String(10), nullable=False)
    
    score_a = db.Column(db.String(50))
    score_b = db.Column(db.String(50))
    score_submission_a = db.Column(db.Text)
    score_submission_b = db.Column(db.Text)
    score_submitted_by_a = db.Column(db.Boolean, default=False)
    score_submitted_by_b = db.Column(db.Boolean, default=False)
    
    team_a_score_set1 = db.Column(db.Integer, nullable=True)
    team_a_score_set2 = db.Column(db.Integer, nullable=True)
    team_a_score_set3 = db.Column(db.Integer, nullable=True)
    team_b_score_set1 = db.Column(db.Integer, nullable=True)
    team_b_score_set2 = db.Column(db.Integer, nullable=True)
    team_b_score_set3 = db.Column(db.Integer, nullable=True)
    
    team_a_submitted = db.Column(db.Boolean, default=False)
    team_b_submitted = db.Column(db.Boolean, default=False)
    
    status = db.Column(db.String(30), default="pending")
    
    winner_id = db.Column(db.Integer, nullable=True)
    sets_a = db.Column(db.Integer, default=0)
    sets_b = db.Column(db.Integer, default=0)
    games_a = db.Column(db.Integer, default=0)
    games_b = db.Column(db.Integer, default=0)
    
    verified = db.Column(db.Boolean, default=False)
    disputed = db.Column(db.Boolean, default=False)
    stats_calculated = db.Column(db.Boolean, default=False)
    
    winner_old_rank = db.Column(db.Integer, nullable=True)
    winner_new_rank = db.Column(db.Integer, nullable=True)
    loser_old_rank = db.Column(db.Integer, nullable=True)
    loser_new_rank = db.Column(db.Integer, nullable=True)
    
    match_date = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    
    reported_no_show_team_id = db.Column(db.Integer, nullable=True)
    reported_by_team_id = db.Column(db.Integer, nullable=True)
    no_show_report_date = db.Column(db.DateTime, nullable=True)
    no_show_verified = db.Column(db.Boolean, default=False)
    no_show_notes = db.Column(db.Text, nullable=True)


class AmericanoTournament(db.Model):
    __tablename__ = 'americano_tournament'
    
    id = db.Column(db.Integer, primary_key=True)
    tournament_date = db.Column(db.DateTime, nullable=False)
    gender = db.Column(db.String(10), nullable=False)
    location = db.Column(db.String(200), nullable=True)
    status = db.Column(db.String(20), default="setup")
    total_rounds = db.Column(db.Integer, default=0)
    participating_free_agents = db.Column(db.Text, nullable=True)
    
    # Points-based format fields
    scoring_format = db.Column(db.String(20), default="points")  # Always "points"
    points_per_match = db.Column(db.Integer, default=24)  # 16, 24, or 32
    time_limit_minutes = db.Column(db.Integer, default=20)  # 10 or 20
    serves_before_rotation = db.Column(db.Integer, default=2)  # 2 or 4
    
    created_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)


class AmericanoMatch(db.Model):
    __tablename__ = 'americano_match'
    
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, nullable=False)
    round_number = db.Column(db.Integer, nullable=False)
    court_number = db.Column(db.Integer, nullable=True)
    
    player1_id = db.Column(db.Integer, nullable=False)
    player2_id = db.Column(db.Integer, nullable=False)
    player3_id = db.Column(db.Integer, nullable=False)
    player4_id = db.Column(db.Integer, nullable=False)
    
    # Points-based scoring (Team A = Player1+Player2, Team B = Player3+Player4)
    score_team_a = db.Column(db.Integer, default=0)  # Total points scored by Team A
    score_team_b = db.Column(db.Integer, default=0)  # Total points scored by Team B
    status = db.Column(db.String(20), default="pending")
    
    # Individual points based on team score
    points_player1 = db.Column(db.Integer, default=0)
    points_player2 = db.Column(db.Integer, default=0)
    points_player3 = db.Column(db.Integer, default=0)
    points_player4 = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime, nullable=True)


class LadderSettings(db.Model):
    __tablename__ = 'ladder_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    challenge_acceptance_hours = db.Column(db.Integer, default=48)
    max_challenge_rank_difference = db.Column(db.Integer, default=3)
    acceptance_penalty_ranks = db.Column(db.Integer, default=1)
    match_completion_days = db.Column(db.Integer, default=7)
    completion_penalty_ranks = db.Column(db.Integer, default=1)
    holiday_mode_grace_weeks = db.Column(db.Integer, default=2)
    holiday_mode_weekly_penalty_ranks = db.Column(db.Integer, default=1)
    min_matches_per_month = db.Column(db.Integer, default=2)
    inactivity_penalty_ranks = db.Column(db.Integer, default=3)
    no_show_penalty_ranks = db.Column(db.Integer, default=1)
    men_registration_open = db.Column(db.Boolean, default=True)
    women_registration_open = db.Column(db.Boolean, default=True)
    mixed_registration_open = db.Column(db.Boolean, default=True)