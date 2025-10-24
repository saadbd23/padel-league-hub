
"""
Background Task Runner for BD Padel League
Runs scheduled tasks periodically while the app is running.

This script runs in the background alongside the main Flask app.
"""

import time
import threading
from datetime import datetime
from scheduled_tasks import send_walkover_warnings, send_match_reminders

def run_hourly_tasks():
    """Tasks that run every hour"""
    while True:
        try:
            hour = datetime.now().hour
            
            # Run match reminders every hour
            print(f"[{datetime.now()}] Running hourly tasks...")
            send_match_reminders()
            
            # Run walkover warnings at 10 AM daily
            if hour == 10:
                print(f"[{datetime.now()}] Running daily tasks...")
                send_walkover_warnings()
            
        except Exception as e:
            print(f"[ERROR] Scheduled task failed: {e}")
        
        # Wait 1 hour
        time.sleep(3600)

if __name__ == "__main__":
    print("[BACKGROUND TASKS] Starting automated notification system...")
    print("[BACKGROUND TASKS] Match reminders: Every hour")
    print("[BACKGROUND TASKS] Walkover warnings: Daily at 10 AM")
    
    # Run in background thread
    task_thread = threading.Thread(target=run_hourly_tasks, daemon=True)
    task_thread.start()
    
    # Keep main thread alive
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n[BACKGROUND TASKS] Shutting down...")
