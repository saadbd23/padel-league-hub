
"""
Migration script to add email column to free_agent table
Run this once to update the PostgreSQL database schema
"""
import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv(override=True)

# Get database URL
database_url = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URI")

# Fix for Render: postgres:// -> postgresql://
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

if not database_url:
    print("❌ DATABASE_URL not found in environment variables")
    exit(1)

print(f"🔗 Connecting to database...")

engine = create_engine(database_url)

try:
    with engine.connect() as conn:
        # Check if email column already exists
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='free_agent' AND column_name='email'
        """))
        
        if result.fetchone():
            print("✅ Email column already exists in free_agent table")
        else:
            # Add email column
            print("📝 Adding email column to free_agent table...")
            conn.execute(text("""
                ALTER TABLE free_agent 
                ADD COLUMN email VARCHAR(120)
            """))
            conn.commit()
            print("✅ Email column added successfully!")
        
        # Verify the column exists
        result = conn.execute(text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name='free_agent'
            ORDER BY ordinal_position
        """))
        
        print("\n📊 Current free_agent table schema:")
        for row in result:
            print(f"  - {row[0]}: {row[1]}")
        
        print("\n✅ Migration completed successfully!")
        
except Exception as e:
    print(f"❌ Migration failed: {e}")
    exit(1)
