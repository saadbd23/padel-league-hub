"""
Database Initialization Script for Production
Creates all tables in the database. Run this on first deployment.

Usage: python init_db.py
"""

import os
from dotenv import load_dotenv
from app import app, db

load_dotenv()

def init_database():
    """Initialize the database with all tables"""
    with app.app_context():
        print("🔧 Initializing database...")
        print(f"📍 Database URI: {app.config['SQLALCHEMY_DATABASE_URI'][:50]}...")
        
        # Create all tables
        db.create_all()
        
        print("✅ Database initialized successfully!")
        print("📋 Tables created:")
        print("   - teams")
        print("   - players")
        print("   - free_agents")
        print("   - matches")
        print("   - reschedules")
        print("   - substitutes")

if __name__ == "__main__":
    init_database()

