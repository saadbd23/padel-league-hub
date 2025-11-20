
import os
from dotenv import load_dotenv
from flask import Flask
from models import db
from sqlalchemy import text

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

def migrate_mixed_ladder_fields():
    """Add player1_gender and player2_gender columns to ladder_team table"""
    with app.app_context():
        print("🔧 Adding Mixed ladder fields to ladder_team table...")
        
        try:
            with db.engine.connect() as conn:
                if database_url.startswith("postgresql://"):
                    print("Running PostgreSQL migration...")
                    
                    # Add player1_gender column
                    conn.execute(text("""
                        ALTER TABLE ladder_team 
                        ADD COLUMN IF NOT EXISTS player1_gender VARCHAR(10);
                    """))
                    print("   ✅ player1_gender")
                    
                    # Add player2_gender column
                    conn.execute(text("""
                        ALTER TABLE ladder_team 
                        ADD COLUMN IF NOT EXISTS player2_gender VARCHAR(10);
                    """))
                    print("   ✅ player2_gender")
                    
                    conn.commit()
                    
                else:
                    print("Running SQLite migration...")
                    
                    # SQLite - check if columns exist first
                    result = conn.execute(text("PRAGMA table_info(ladder_team)"))
                    columns = [row[1] for row in result]
                    
                    if 'player1_gender' not in columns:
                        conn.execute(text("""
                            ALTER TABLE ladder_team 
                            ADD COLUMN player1_gender VARCHAR(10);
                        """))
                        print("   ✅ player1_gender")
                    else:
                        print("   ⏭️ player1_gender already exists")
                    
                    if 'player2_gender' not in columns:
                        conn.execute(text("""
                            ALTER TABLE ladder_team 
                            ADD COLUMN player2_gender VARCHAR(10);
                        """))
                        print("   ✅ player2_gender")
                    else:
                        print("   ⏭️ player2_gender already exists")
                    
                    conn.commit()
            
            print("\n✅ Migration completed successfully!")
            print("📋 Fields added to ladder_team:")
            print("   - player1_gender (for Mixed teams)")
            print("   - player2_gender (for Mixed teams)")
            
        except Exception as e:
            print(f"❌ Error during migration: {e}")
            raise

if __name__ == "__main__":
    migrate_mixed_ladder_fields()
