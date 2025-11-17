
"""
Migration script to add payment_received field to LadderTeam table
"""
import os
from sqlalchemy import create_engine, text

# Get database URL
database_url = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URI")

if not database_url:
    print("ERROR: No DATABASE_URL found")
    exit(1)

# Fix postgres:// to postgresql://
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

print(f"Connecting to database...")
engine = create_engine(database_url)

try:
    with engine.connect() as conn:
        # Add payment_received column with default False
        print("Adding payment_received column to ladder_team table...")
        conn.execute(text("""
            ALTER TABLE ladder_team 
            ADD COLUMN IF NOT EXISTS payment_received BOOLEAN DEFAULT FALSE
        """))
        conn.commit()
        
        print("✓ Successfully added payment_received column")
        print("\nAll existing teams have payment_received = False by default")
        print("Admin can now mark teams as paid in the admin panel")
        
except Exception as e:
    print(f"ERROR: Migration failed - {e}")
    exit(1)

print("\n✓ Migration completed successfully!")
