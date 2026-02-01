"""
Migration script for Americano Tournament Open Registration
Creates the AmericanoRegistration table and adds new columns to AmericanoTournament
"""
import os
import sys
from sqlalchemy import create_engine, inspect, text

# Database configuration
database_url = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URI")
if not database_url:
    database_url = "sqlite:///instance/league.db"
    print("Warning: No DATABASE_URL found, using SQLite fallback")

# Fix for Render: postgres:// -> postgresql://
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

engine = create_engine(database_url)


def table_exists(table_name):
    """Check if a table exists in the database"""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def column_exists(table_name, column_name):
    """Check if a column exists in a table"""
    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def run_migration():
    """Run the migration"""
    print("Starting Americano Registration migration...")

    with engine.connect() as conn:
        # 1. Add new columns to americano_tournament table
        tournament_columns = {
            'registration_open': 'BOOLEAN DEFAULT FALSE',
            'registration_deadline': 'TIMESTAMP',
            'max_participants': 'INTEGER DEFAULT 24',
            'public_title': 'VARCHAR(200)',
            'public_description': 'TEXT',
            'num_courts': 'INTEGER DEFAULT 2'
        }

        for col_name, col_type in tournament_columns.items():
            if not column_exists('americano_tournament', col_name):
                try:
                    sql = f'ALTER TABLE americano_tournament ADD COLUMN {col_name} {col_type}'
                    conn.execute(text(sql))
                    conn.commit()
                    print(f"  Added column: americano_tournament.{col_name}")
                except Exception as e:
                    print(f"  Warning: Could not add column {col_name}: {e}")
            else:
                print(f"  Column already exists: americano_tournament.{col_name}")

        # 2. Create americano_registration table if it doesn't exist
        if not table_exists('americano_registration'):
            create_sql = """
            CREATE TABLE americano_registration (
                id SERIAL PRIMARY KEY,
                tournament_id INTEGER NOT NULL REFERENCES americano_tournament(id),
                name VARCHAR(100) NOT NULL,
                phone VARCHAR(20) NOT NULL,
                email VARCHAR(120) NOT NULL,
                gender VARCHAR(10) NOT NULL,
                source_type VARCHAR(20),
                source_id INTEGER,
                ladder_free_agent_id INTEGER REFERENCES ladder_free_agent(id),
                status VARCHAR(20) DEFAULT 'confirmed',
                skill_level VARCHAR(20),
                created_at TIMESTAMP
            )
            """
            # Adjust for SQLite
            if 'sqlite' in database_url:
                create_sql = """
                CREATE TABLE americano_registration (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tournament_id INTEGER NOT NULL REFERENCES americano_tournament(id),
                    name VARCHAR(100) NOT NULL,
                    phone VARCHAR(20) NOT NULL,
                    email VARCHAR(120) NOT NULL,
                    gender VARCHAR(10) NOT NULL,
                    source_type VARCHAR(20),
                    source_id INTEGER,
                    ladder_free_agent_id INTEGER REFERENCES ladder_free_agent(id),
                    status VARCHAR(20) DEFAULT 'confirmed',
                    skill_level VARCHAR(20),
                    created_at TIMESTAMP
                )
                """

            try:
                conn.execute(text(create_sql))
                conn.commit()
                print("  Created table: americano_registration")

                # Create index on phone for faster lookups
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_americano_registration_phone ON americano_registration(phone)"))
                conn.commit()
                print("  Created index: idx_americano_registration_phone")

                # Create index on tournament_id
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_americano_registration_tournament ON americano_registration(tournament_id)"))
                conn.commit()
                print("  Created index: idx_americano_registration_tournament")

            except Exception as e:
                print(f"  Error creating americano_registration table: {e}")
                raise
        else:
            print("  Table already exists: americano_registration")

    print("\nMigration completed successfully!")


if __name__ == "__main__":
    run_migration()
