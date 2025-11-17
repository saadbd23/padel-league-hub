"""
Ladder Match Rank Tracking Fields Migration Script
Adds rank change tracking fields to ladder_match table for displaying rank swap history.

Usage: python migrate_ladder_match_rank_fields.py
"""

import os
from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv()

def migrate_ladder_match_rank_fields():
    """Add rank tracking fields to ladder_match table"""
    from app import app, db
    
    with app.app_context():
        print("🔧 Adding rank tracking fields to ladder_match table...")
        print(f"📍 Database URI: {app.config['SQLALCHEMY_DATABASE_URI'][:50]}...")
        
        try:
            with db.engine.connect() as conn:
                with conn.begin():
                    print("\n📝 Adding rank tracking columns...")
                    
                    conn.execute(text("""
                        ALTER TABLE ladder_match 
                        ADD COLUMN IF NOT EXISTS winner_old_rank INTEGER;
                    """))
                    print("   ✅ winner_old_rank")
                    
                    conn.execute(text("""
                        ALTER TABLE ladder_match 
                        ADD COLUMN IF NOT EXISTS winner_new_rank INTEGER;
                    """))
                    print("   ✅ winner_new_rank")
                    
                    conn.execute(text("""
                        ALTER TABLE ladder_match 
                        ADD COLUMN IF NOT EXISTS loser_old_rank INTEGER;
                    """))
                    print("   ✅ loser_old_rank")
                    
                    conn.execute(text("""
                        ALTER TABLE ladder_match 
                        ADD COLUMN IF NOT EXISTS loser_new_rank INTEGER;
                    """))
                    print("   ✅ loser_new_rank")
            
            print("\n✅ Migration completed successfully!")
            print("📋 Fields added to ladder_match:")
            print("   - winner_old_rank, winner_new_rank")
            print("   - loser_old_rank, loser_new_rank")
            
        except Exception as e:
            print(f"❌ Error during migration: {e}")
            raise

if __name__ == "__main__":
    migrate_ladder_match_rank_fields()
