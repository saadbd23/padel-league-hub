import os
from dotenv import load_dotenv
from flask import Flask
from models import db, LadderSettings

load_dotenv(override=True)

app = Flask(__name__)

database_url = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URI")
if not database_url:
    database_url = "sqlite:///instance/league.db"

if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
}

db.init_app(app)

with app.app_context():
    print("Updating LadderSettings table schema...")
    
    try:
        if database_url.startswith("postgresql://"):
            print("Running PostgreSQL migration...")
            db.session.execute(db.text("""
                ALTER TABLE ladder_settings 
                ADD COLUMN IF NOT EXISTS completion_penalty_ranks INTEGER DEFAULT 1;
            """))
            
            db.session.execute(db.text("""
                ALTER TABLE ladder_settings 
                ADD COLUMN IF NOT EXISTS match_completion_days INTEGER;
            """))
            
            db.session.execute(db.text("""
                UPDATE ladder_settings 
                SET match_completion_days = challenge_completion_days 
                WHERE match_completion_days IS NULL;
            """))
            
            db.session.execute(db.text("""
                ALTER TABLE ladder_settings 
                ADD COLUMN IF NOT EXISTS men_registration_open BOOLEAN DEFAULT TRUE;
            """))
            
            db.session.execute(db.text("""
                UPDATE ladder_settings 
                SET men_registration_open = team_registration_open 
                WHERE men_registration_open IS NULL;
            """))
            
            db.session.execute(db.text("""
                ALTER TABLE ladder_settings 
                ADD COLUMN IF NOT EXISTS women_registration_open BOOLEAN DEFAULT TRUE;
            """))
            
            db.session.execute(db.text("""
                UPDATE ladder_settings 
                SET women_registration_open = free_agent_registration_open 
                WHERE women_registration_open IS NULL;
            """))
            
            db.session.commit()
            print("PostgreSQL migration completed successfully!")
            
        else:
            print("SQLite detected - recreating table with new schema...")
            db.session.execute(db.text("DROP TABLE IF EXISTS ladder_settings_backup"))
            db.session.execute(db.text("""
                CREATE TABLE ladder_settings_backup AS 
                SELECT * FROM ladder_settings
            """))
            
            db.session.execute(db.text("DROP TABLE ladder_settings"))
            db.session.execute(db.text("""
                CREATE TABLE ladder_settings (
                    id INTEGER PRIMARY KEY,
                    challenge_acceptance_hours INTEGER DEFAULT 48,
                    max_challenge_rank_difference INTEGER DEFAULT 3,
                    acceptance_penalty_ranks INTEGER DEFAULT 1,
                    match_completion_days INTEGER DEFAULT 7,
                    completion_penalty_ranks INTEGER DEFAULT 1,
                    holiday_mode_grace_weeks INTEGER DEFAULT 2,
                    holiday_mode_weekly_penalty_ranks INTEGER DEFAULT 1,
                    min_matches_per_month INTEGER DEFAULT 2,
                    inactivity_penalty_ranks INTEGER DEFAULT 3,
                    no_show_penalty_ranks INTEGER DEFAULT 1,
                    men_registration_open BOOLEAN DEFAULT 1,
                    women_registration_open BOOLEAN DEFAULT 1
                )
            """))
            
            db.session.execute(db.text("""
                INSERT INTO ladder_settings (
                    id, challenge_acceptance_hours, max_challenge_rank_difference,
                    acceptance_penalty_ranks, match_completion_days, completion_penalty_ranks,
                    holiday_mode_grace_weeks, holiday_mode_weekly_penalty_ranks,
                    min_matches_per_month, inactivity_penalty_ranks, no_show_penalty_ranks,
                    men_registration_open, women_registration_open
                )
                SELECT 
                    id, challenge_acceptance_hours, max_challenge_rank_difference,
                    acceptance_penalty_ranks, 
                    COALESCE(challenge_completion_days, 7), 1,
                    holiday_mode_grace_weeks, holiday_mode_weekly_penalty_ranks,
                    min_matches_per_month, inactivity_penalty_ranks, no_show_penalty_ranks,
                    COALESCE(team_registration_open, 1), 
                    COALESCE(free_agent_registration_open, 1)
                FROM ladder_settings_backup
            """))
            
            db.session.execute(db.text("DROP TABLE ladder_settings_backup"))
            db.session.commit()
            print("SQLite migration completed successfully!")
            
        settings = LadderSettings.query.first()
        if not settings:
            print("Creating default LadderSettings record...")
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
            print("Default settings created!")
        else:
            print(f"Existing settings found: {settings.__dict__}")
            
        print("\nMigration completed successfully!")
        
    except Exception as e:
        print(f"Error during migration: {e}")
        db.session.rollback()
        raise
