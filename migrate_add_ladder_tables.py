"""
Ladder Tables Migration Script
Adds ladder tournament tables to existing database without affecting league tables.

Usage: python migrate_add_ladder_tables.py
"""

import os
from dotenv import load_dotenv
from app import app, db
from models import (
    LadderTeam, LadderFreeAgent, LadderChallenge, LadderMatch,
    AmericanoTournament, AmericanoMatch, LadderSettings
)

load_dotenv()

def migrate_ladder_tables():
    """Add ladder tables to existing database"""
    with app.app_context():
        print("🔧 Adding ladder tables to database...")
        print(f"📍 Database URI: {app.config['SQLALCHEMY_DATABASE_URI'][:50]}...")
        
        try:
            # Create only the ladder tables
            db.create_all()
            
            # Initialize default ladder settings if not exists
            settings = LadderSettings.query.first()
            if not settings:
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
                    free_agent_partner_selection_days=3,
                    team_registration_open=True,
                    free_agent_registration_open=True
                )
                db.session.add(settings)
                db.session.commit()
                print("✅ Default ladder settings created")
            
            print("✅ Ladder tables added successfully!")
            print("📋 New tables created:")
            print("   - ladder_team")
            print("   - ladder_free_agent")
            print("   - ladder_challenge")
            print("   - ladder_match")
            print("   - americano_tournament")
            print("   - americano_match")
            print("   - ladder_settings")
            
        except Exception as e:
            print(f"❌ Error during migration: {e}")
            raise

if __name__ == "__main__":
    migrate_ladder_tables()
