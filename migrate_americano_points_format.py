
"""
Migration script to add points-based format fields to AmericanoTournament and update AmericanoMatch
"""

from app import app, db
from models import AmericanoTournament, AmericanoMatch
from sqlalchemy import text

def migrate_americano_points_format():
    with app.app_context():
        try:
            # Add new columns to AmericanoTournament
            with db.engine.connect() as conn:
                # Add scoring_format column
                try:
                    conn.execute(text("""
                        ALTER TABLE americano_tournament 
                        ADD COLUMN scoring_format VARCHAR(20) DEFAULT 'points'
                    """))
                    conn.commit()
                    print("✓ Added scoring_format column to americano_tournament")
                except Exception as e:
                    if "already exists" not in str(e).lower():
                        print(f"⚠ Error adding scoring_format: {e}")
                
                # Add points_per_match column
                try:
                    conn.execute(text("""
                        ALTER TABLE americano_tournament 
                        ADD COLUMN points_per_match INTEGER DEFAULT 24
                    """))
                    conn.commit()
                    print("✓ Added points_per_match column to americano_tournament")
                except Exception as e:
                    if "already exists" not in str(e).lower():
                        print(f"⚠ Error adding points_per_match: {e}")
                
                # Add time_limit_minutes column
                try:
                    conn.execute(text("""
                        ALTER TABLE americano_tournament 
                        ADD COLUMN time_limit_minutes INTEGER DEFAULT 20
                    """))
                    conn.commit()
                    print("✓ Added time_limit_minutes column to americano_tournament")
                except Exception as e:
                    if "already exists" not in str(e).lower():
                        print(f"⚠ Error adding time_limit_minutes: {e}")
                
                # Add serves_before_rotation column
                try:
                    conn.execute(text("""
                        ALTER TABLE americano_tournament 
                        ADD COLUMN serves_before_rotation INTEGER DEFAULT 2
                    """))
                    conn.commit()
                    print("✓ Added serves_before_rotation column to americano_tournament")
                except Exception as e:
                    if "already exists" not in str(e).lower():
                        print(f"⚠ Error adding serves_before_rotation: {e}")
            
            print("\n✅ Migration completed successfully!")
            print("\nNote: AmericanoMatch.score_team_a and score_team_b are now INTEGER fields.")
            print("Existing string values will be converted to integers automatically.")
            
        except Exception as e:
            print(f"❌ Migration failed: {e}")
            db.session.rollback()

if __name__ == "__main__":
    migrate_americano_points_format()
