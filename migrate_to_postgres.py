"""
Database Migration Script: SQLite to PostgreSQL
Run this script to migrate your local SQLite data to production PostgreSQL database.

Usage:
1. Set your production DATABASE_URL in .env:
   DATABASE_URL=postgresql://user:password@host:port/database
   
2. Run: python migrate_to_postgres.py
"""

import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from models import Team, FreeAgent, Match, Reschedule, Substitute, Player, db

load_dotenv()

# Source database (SQLite)
SQLITE_URI = "sqlite:///instance/league.db"

# Target database (PostgreSQL from environment)
POSTGRES_URI = os.environ.get("DATABASE_URL")

if not POSTGRES_URI:
    print("❌ ERROR: DATABASE_URL not found in environment variables!")
    print("Please set it in your .env file or environment.")
    sys.exit(1)

# Handle Render's postgres:// vs postgresql:// format
if POSTGRES_URI.startswith("postgres://"):
    POSTGRES_URI = POSTGRES_URI.replace("postgres://", "postgresql://", 1)

print("🔄 Starting database migration...")
print(f"📂 Source: {SQLITE_URI}")
print(f"🎯 Target: {POSTGRES_URI[:50]}...")

# Create engines
source_engine = create_engine(SQLITE_URI)
target_engine = create_engine(POSTGRES_URI)

# Create sessions
SourceSession = sessionmaker(bind=source_engine)
TargetSession = sessionmaker(bind=target_engine)

source_session = SourceSession()
target_session = TargetSession()

def migrate_data():
    """Migrate all data from SQLite to PostgreSQL"""
    
    try:
        # Create all tables in target database
        print("\n📋 Creating tables in target database...")
        from models import db
        # Import app to initialize db
        from app import app
        with app.app_context():
            app.config["SQLALCHEMY_DATABASE_URI"] = POSTGRES_URI
            db.init_app(app)
            db.create_all()
        print("✅ Tables created successfully!")
        
        # Migrate Teams
        print("\n👥 Migrating Teams...")
        teams = source_session.query(Team).all()
        for team in teams:
            # Create new team object (detached from source session)
            new_team = Team(
                id=team.id,
                team_name=team.team_name,
                player1_name=team.player1_name,
                player1_phone=team.player1_phone,
                player1_email=team.player1_email,
                player2_name=team.player2_name,
                player2_phone=team.player2_phone,
                player2_email=team.player2_email,
                player2_confirmed=team.player2_confirmed,
                team_type=team.team_type,
                wins=team.wins,
                losses=team.losses,
                points=team.points,
                sets_for=team.sets_for,
                sets_against=team.sets_against,
                games_for=team.games_for,
                games_against=team.games_against,
                confirmation_token=team.confirmation_token,
                whatsapp_token=team.whatsapp_token,
                created_at=team.created_at
            )
            target_session.merge(new_team)
        target_session.commit()
        print(f"✅ Migrated {len(teams)} teams")
        
        # Migrate Players
        print("\n🎾 Migrating Players...")
        players = source_session.query(Player).all()
        for player in players:
            new_player = Player(
                id=player.id,
                name=player.name,
                phone=player.phone,
                email=player.email,
                matches_played=player.matches_played,
                matches_won=player.matches_won,
                matches_lost=player.matches_lost,
                sets_won=player.sets_won,
                sets_lost=player.sets_lost,
                games_won=player.games_won,
                games_lost=player.games_lost,
                created_at=player.created_at
            )
            target_session.merge(new_player)
        target_session.commit()
        print(f"✅ Migrated {len(players)} players")
        
        # Migrate Free Agents
        print("\n🆓 Migrating Free Agents...")
        free_agents = source_session.query(FreeAgent).all()
        for agent in free_agents:
            new_agent = FreeAgent(
                id=agent.id,
                name=agent.name,
                phone=agent.phone,
                email=agent.email,
                paired=agent.paired,
                whatsapp_token=agent.whatsapp_token,
                created_at=agent.created_at
            )
            target_session.merge(new_agent)
        target_session.commit()
        print(f"✅ Migrated {len(free_agents)} free agents")
        
        # Migrate Matches
        print("\n🏆 Migrating Matches...")
        matches = source_session.query(Match).all()
        for match in matches:
            new_match = Match(
                id=match.id,
                round_number=match.round_number,
                team_a_id=match.team_a_id,
                team_b_id=match.team_b_id,
                booking_confirmed=match.booking_confirmed,
                booking_time=match.booking_time,
                booking_location=match.booking_location,
                whatsapp_sent=match.whatsapp_sent,
                score=match.score,
                sets_a=match.sets_a,
                sets_b=match.sets_b,
                games_a=match.games_a,
                games_b=match.games_b,
                stats_calculated=match.stats_calculated,
                created_at=match.created_at
            )
            target_session.merge(new_match)
        target_session.commit()
        print(f"✅ Migrated {len(matches)} matches")
        
        # Migrate Reschedules
        print("\n📅 Migrating Reschedule Requests...")
        reschedules = source_session.query(Reschedule).all()
        for reschedule in reschedules:
            new_reschedule = Reschedule(
                id=reschedule.id,
                match_id=reschedule.match_id,
                requested_by=reschedule.requested_by,
                new_time=reschedule.new_time,
                new_location=reschedule.new_location,
                reason=reschedule.reason,
                status=reschedule.status,
                created_at=reschedule.created_at
            )
            target_session.merge(new_reschedule)
        target_session.commit()
        print(f"✅ Migrated {len(reschedules)} reschedule requests")
        
        # Migrate Substitutes
        print("\n🔄 Migrating Substitutes...")
        substitutes = source_session.query(Substitute).all()
        for substitute in substitutes:
            new_substitute = Substitute(
                id=substitute.id,
                match_id=substitute.match_id,
                original_team_id=substitute.original_team_id,
                original_player_name=substitute.original_player_name,
                substitute_name=substitute.substitute_name,
                substitute_phone=substitute.substitute_phone,
                substitute_email=getattr(substitute, 'substitute_email', None),
                created_at=substitute.created_at
            )
            target_session.merge(new_substitute)
        target_session.commit()
        print(f"✅ Migrated {len(substitutes)} substitute records")
        
        print("\n🎉 Migration completed successfully!")
        print(f"📊 Summary:")
        print(f"   - Teams: {len(teams)}")
        print(f"   - Players: {len(players)}")
        print(f"   - Free Agents: {len(free_agents)}")
        print(f"   - Matches: {len(matches)}")
        print(f"   - Reschedules: {len(reschedules)}")
        print(f"   - Substitutes: {len(substitutes)}")
        
    except Exception as e:
        print(f"\n❌ ERROR during migration: {e}")
        target_session.rollback()
        raise
    finally:
        source_session.close()
        target_session.close()

if __name__ == "__main__":
    print("⚠️  WARNING: This will copy data to your production database!")
    print("Make sure you have backed up your data before proceeding.")
    response = input("\nContinue? (yes/no): ")
    
    if response.lower() in ['yes', 'y']:
        migrate_data()
    else:
        print("❌ Migration cancelled.")

