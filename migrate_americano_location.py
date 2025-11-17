"""
Migration script to add location column to americano_tournament table
Run this once to update the database schema
"""

import os
from sqlalchemy import create_engine, text

# Get database URL from environment
database_url = os.environ.get('DATABASE_URL')
if not database_url:
    print("ERROR: DATABASE_URL environment variable not set")
    exit(1)

# Create engine
engine = create_engine(database_url)

print("Adding location column to americano_tournament table...")

try:
    with engine.connect() as conn:
        # Add location column if it doesn't exist
        conn.execute(text("""
            ALTER TABLE americano_tournament 
            ADD COLUMN IF NOT EXISTS location VARCHAR(200);
        """))
        conn.commit()
        print("✅ Successfully added location column to americano_tournament table")
        
except Exception as e:
    print(f"❌ Error during migration: {e}")
    exit(1)

print("\n✅ Migration completed successfully!")
