
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

def migrate_add_mixed_registration():
    """Add mixed_registration_open column to ladder_settings table"""
    with app.app_context():
        print("🔧 Adding mixed_registration_open field to ladder_settings table...")
        
        try:
            with db.engine.connect() as conn:
                if database_url.startswith("postgresql://"):
                    print("Running PostgreSQL migration...")
                    
                    # Add mixed_registration_open column
                    conn.execute(text("""
                        ALTER TABLE ladder_settings 
                        ADD COLUMN IF NOT EXISTS mixed_registration_open BOOLEAN DEFAULT TRUE;
                    """))
                    print("   ✅ mixed_registration_open")
                    
                    conn.commit()
                    
                else:
                    print("Running SQLite migration...")
                    
                    # SQLite - check if column exists first
                    result = conn.execute(text("PRAGMA table_info(ladder_settings)"))
                    columns = [row[1] for row in result]
                    
                    if 'mixed_registration_open' not in columns:
                        conn.execute(text("""
                            ALTER TABLE ladder_settings 
                            ADD COLUMN mixed_registration_open BOOLEAN DEFAULT 1;
                        """))
                        print("   ✅ mixed_registration_open")
                    else:
                        print("   ⏭️ mixed_registration_open already exists")
                    
                    conn.commit()
            
            print("\n✅ Migration completed successfully!")
            print("📋 Field added to ladder_settings:")
            print("   - mixed_registration_open (for controlling Mixed ladder registration)")
            
        except Exception as e:
            print(f"❌ Error during migration: {e}")
            raise

if __name__ == "__main__":
    migrate_add_mixed_registration()
