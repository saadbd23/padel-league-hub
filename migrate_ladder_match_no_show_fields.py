"""
Ladder Match No-Show Reporting Fields Migration Script
Adds no-show reporting fields to ladder_match table for tracking no-show incidents.

Usage: python migrate_ladder_match_no_show_fields.py
"""

import os
from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv()

def migrate_ladder_match_no_show_fields():
    """Add no-show reporting fields to ladder_match table"""
    from app import app, db
    
    with app.app_context():
        print("🔧 Adding no-show reporting fields to ladder_match table...")
        print(f"📍 Database URI: {app.config['SQLALCHEMY_DATABASE_URI'][:50]}...")
        
        try:
            with db.engine.connect() as conn:
                with conn.begin():
                    print("\n📝 Adding no-show reporting columns...")
                    
                    conn.execute(text("""
                        ALTER TABLE ladder_match 
                        ADD COLUMN IF NOT EXISTS reported_no_show_team_id INTEGER;
                    """))
                    print("   ✅ reported_no_show_team_id")
                    
                    conn.execute(text("""
                        ALTER TABLE ladder_match 
                        ADD COLUMN IF NOT EXISTS reported_by_team_id INTEGER;
                    """))
                    print("   ✅ reported_by_team_id")
                    
                    conn.execute(text("""
                        ALTER TABLE ladder_match 
                        ADD COLUMN IF NOT EXISTS no_show_report_date TIMESTAMP;
                    """))
                    print("   ✅ no_show_report_date")
                    
                    conn.execute(text("""
                        ALTER TABLE ladder_match 
                        ADD COLUMN IF NOT EXISTS no_show_verified BOOLEAN DEFAULT FALSE;
                    """))
                    print("   ✅ no_show_verified")
                    
                    conn.execute(text("""
                        ALTER TABLE ladder_match 
                        ADD COLUMN IF NOT EXISTS no_show_notes TEXT;
                    """))
                    print("   ✅ no_show_notes")
            
            print("\n✅ Migration completed successfully!")
            print("📋 Fields added to ladder_match:")
            print("   - reported_no_show_team_id (which team was reported)")
            print("   - reported_by_team_id (which team reported)")
            print("   - no_show_report_date (when the report was filed)")
            print("   - no_show_verified (admin approval status)")
            print("   - no_show_notes (admin notes)")
            
        except Exception as e:
            print(f"❌ Error during migration: {e}")
            raise

if __name__ == "__main__":
    migrate_ladder_match_no_show_fields()
