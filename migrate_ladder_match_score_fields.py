"""
Ladder Match Score Fields Migration Script
Adds individual set score fields and status field to ladder_match table for score submission system.

Usage: python migrate_ladder_match_score_fields.py
"""

import os
from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv()

def migrate_ladder_match_score_fields():
    """Add score submission fields to ladder_match table"""
    from app import app, db
    
    with app.app_context():
        print("🔧 Adding score submission fields to ladder_match table...")
        print(f"📍 Database URI: {app.config['SQLALCHEMY_DATABASE_URI'][:50]}...")
        
        try:
            with db.engine.connect() as conn:
                with conn.begin():
                    print("\n📝 Adding individual set score columns...")
                    
                    conn.execute(text("""
                        ALTER TABLE ladder_match 
                        ADD COLUMN IF NOT EXISTS team_a_score_set1 INTEGER;
                    """))
                    print("   ✅ team_a_score_set1")
                    
                    conn.execute(text("""
                        ALTER TABLE ladder_match 
                        ADD COLUMN IF NOT EXISTS team_a_score_set2 INTEGER;
                    """))
                    print("   ✅ team_a_score_set2")
                    
                    conn.execute(text("""
                        ALTER TABLE ladder_match 
                        ADD COLUMN IF NOT EXISTS team_a_score_set3 INTEGER;
                    """))
                    print("   ✅ team_a_score_set3")
                    
                    conn.execute(text("""
                        ALTER TABLE ladder_match 
                        ADD COLUMN IF NOT EXISTS team_b_score_set1 INTEGER;
                    """))
                    print("   ✅ team_b_score_set1")
                    
                    conn.execute(text("""
                        ALTER TABLE ladder_match 
                        ADD COLUMN IF NOT EXISTS team_b_score_set2 INTEGER;
                    """))
                    print("   ✅ team_b_score_set2")
                    
                    conn.execute(text("""
                        ALTER TABLE ladder_match 
                        ADD COLUMN IF NOT EXISTS team_b_score_set3 INTEGER;
                    """))
                    print("   ✅ team_b_score_set3")
                    
                    print("\n📝 Adding submission tracking columns...")
                    
                    conn.execute(text("""
                        ALTER TABLE ladder_match 
                        ADD COLUMN IF NOT EXISTS team_a_submitted BOOLEAN DEFAULT FALSE;
                    """))
                    print("   ✅ team_a_submitted")
                    
                    conn.execute(text("""
                        ALTER TABLE ladder_match 
                        ADD COLUMN IF NOT EXISTS team_b_submitted BOOLEAN DEFAULT FALSE;
                    """))
                    print("   ✅ team_b_submitted")
                    
                    print("\n📝 Adding status column...")
                    
                    conn.execute(text("""
                        ALTER TABLE ladder_match 
                        ADD COLUMN IF NOT EXISTS status VARCHAR(30) DEFAULT 'pending';
                    """))
                    print("   ✅ status")
                    
                    conn.execute(text("""
                        UPDATE ladder_match 
                        SET status = 'pending' 
                        WHERE status IS NULL;
                    """))
                    print("   ✅ Set default status for existing records")
            
            print("\n✅ Migration completed successfully!")
            print("📋 Fields added to ladder_match:")
            print("   - team_a_score_set1, team_a_score_set2, team_a_score_set3")
            print("   - team_b_score_set1, team_b_score_set2, team_b_score_set3")
            print("   - team_a_submitted, team_b_submitted")
            print("   - status")
            
        except Exception as e:
            print(f"❌ Error during migration: {e}")
            raise

if __name__ == "__main__":
    migrate_ladder_match_score_fields()
