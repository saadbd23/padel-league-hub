
"""
Scheduled Tasks for BD Padel League
Handles automated email notifications for:
- Walkover warnings (before deadlines)
- Match reminders (24 hours before matches)

Run this script periodically (e.g., via cron or background worker)
"""

import os
from datetime import datetime, timedelta
from models import db, Match, Team, Reschedule
from utils import send_email_notification
from app import app

def send_walkover_warnings():
    """
    Send warnings to teams that haven't completed matches before deadlines.
    Run this daily at 10 AM to give teams advance warning.
    """
    with app.app_context():
        now = datetime.now()
        today = now.date()
        
        warnings_sent = 0
        
        # Check regular matches (Sunday deadline)
        if today.weekday() >= 4:  # Friday, Saturday, or Sunday
            # Find matches that are still scheduled and approaching Sunday deadline
            upcoming_sunday = today + timedelta(days=(6 - today.weekday()))
            
            scheduled_matches = Match.query.filter(
                Match.status == "scheduled",
                Match.round.isnot(None)
            ).all()
            
            for match in scheduled_matches:
                # Skip if this match has a pending reschedule
                has_reschedule = Reschedule.query.filter_by(
                    match_id=match.id,
                    status="pending"
                ).first()
                
                if has_reschedule:
                    continue
                
                # Get teams
                team_a = Team.query.get(match.team_a_id)
                team_b = Team.query.get(match.team_b_id)
                
                if not team_a or not team_b:
                    continue
                
                # Calculate round end date
                from app import get_round_start_date
                round_start = get_round_start_date(match.round)
                if round_start:
                    round_end = round_start + timedelta(days=6)  # Sunday
                    days_until_deadline = (round_end - today).days
                    
                    # Send warning if 2 days or less until deadline
                    if 0 <= days_until_deadline <= 2 and not match.booking_confirmed:
                        warning_body = f"""Hi!

⚠️ DEADLINE WARNING - Match Not Completed

Your Round {match.round} match is approaching the deadline!

Match Details:
- Opponent: {team_b.team_name if match.team_a_id == team_a.id else team_a.team_name}
- Deadline: Sunday {round_end.strftime('%B %d')} at 23:59
- Days Remaining: {days_until_deadline}

⚠️ If not completed by Sunday 23:59, an automatic WALKOVER will be awarded to your opponent.

📋 Action Required:
1. Coordinate with opponent IMMEDIATELY
2. Book a court and play the match
3. Submit scores after completion

- BD Padel League
"""
                        # Send to both teams
                        if team_a.player1_email:
                            send_email_notification(team_a.player1_email, f"⚠️ URGENT: Match Deadline - {days_until_deadline} Days Left", warning_body)
                        if team_a.player2_email:
                            send_email_notification(team_a.player2_email, f"⚠️ URGENT: Match Deadline - {days_until_deadline} Days Left", warning_body)
                        if team_b.player1_email:
                            send_email_notification(team_b.player1_email, f"⚠️ URGENT: Match Deadline - {days_until_deadline} Days Left", warning_body)
                        if team_b.player2_email:
                            send_email_notification(team_b.player2_email, f"⚠️ URGENT: Match Deadline - {days_until_deadline} Days Left", warning_body)
                        
                        warnings_sent += 1
        
        # Check makeup matches (Wednesday deadline)
        pending_reschedules = Reschedule.query.filter_by(status="approved").all()
        
        for reschedule in pending_reschedules:
            match = Match.query.get(reschedule.match_id)
            if not match or match.status == "completed":
                continue
            
            # Parse the proposed time to get the Wednesday deadline
            if reschedule.proposed_time and " at " in reschedule.proposed_time:
                try:
                    date_str = reschedule.proposed_time.split(" at ")[0]
                    proposed_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    
                    # Find Wednesday of that week
                    proposed_weekday = proposed_date.weekday()
                    if proposed_weekday in [0, 1, 2]:
                        days_to_wednesday = 2 - proposed_weekday
                        wednesday_deadline = proposed_date + timedelta(days=days_to_wednesday)
                        days_until_deadline = (wednesday_deadline - today).days
                        
                        # Send warning if 1 day or less until Wednesday deadline
                        if 0 <= days_until_deadline <= 1 and not match.booking_confirmed:
                            requester_team = Team.query.get(reschedule.requester_team_id)
                            opponent_id = match.team_b_id if match.team_a_id == requester_team.id else match.team_a_id
                            opponent_team = Team.query.get(opponent_id)
                            
                            if requester_team and opponent_team:
                                makeup_warning = f"""Hi!

⚠️ URGENT: MAKEUP MATCH DEADLINE WARNING

Your rescheduled match is approaching the absolute deadline!

Match Details:
- Round: {match.round}
- Opponent: {opponent_team.team_name if reschedule.requester_team_id == requester_team.id else requester_team.team_name}
- Wednesday Deadline: {wednesday_deadline.strftime('%B %d')} at 23:59
- Days Remaining: {days_until_deadline}

⚠️ If not completed by Wednesday 23:59, an automatic WALKOVER will be awarded to {opponent_team.team_name if reschedule.requester_team_id == requester_team.id else requester_team.team_name}.

This is your FINAL WARNING. Complete the match IMMEDIATELY.

- BD Padel League
"""
                                # Send to both teams
                                if requester_team.player1_email:
                                    send_email_notification(requester_team.player1_email, f"🚨 FINAL WARNING: Makeup Match Deadline - {days_until_deadline} Days", makeup_warning)
                                if requester_team.player2_email:
                                    send_email_notification(requester_team.player2_email, f"🚨 FINAL WARNING: Makeup Match Deadline - {days_until_deadline} Days", makeup_warning)
                                if opponent_team.player1_email:
                                    send_email_notification(opponent_team.player1_email, f"🚨 FINAL WARNING: Makeup Match Deadline - {days_until_deadline} Days", makeup_warning)
                                if opponent_team.player2_email:
                                    send_email_notification(opponent_team.player2_email, f"🚨 FINAL WARNING: Makeup Match Deadline - {days_until_deadline} Days", makeup_warning)
                                
                                warnings_sent += 1
                except:
                    continue
        
        print(f"[SCHEDULED TASK] Sent {warnings_sent} walkover warnings")
        return warnings_sent


def send_match_reminders():
    """
    Send 24-hour reminders for upcoming matches.
    Run this hourly to catch matches scheduled for tomorrow.
    """
    with app.app_context():
        now = datetime.now()
        tomorrow = now + timedelta(hours=24)
        
        reminders_sent = 0
        
        # Find matches with confirmed bookings in the next 24-48 hours
        matches = Match.query.filter(
            Match.booking_confirmed == True,
            Match.reminder_sent == False,
            Match.match_datetime.isnot(None)
        ).all()
        
        for match in matches:
            # Check if match is within 24-48 hour window
            time_until_match = match.match_datetime - now
            hours_until_match = time_until_match.total_seconds() / 3600
            
            if 24 <= hours_until_match <= 48:
                team_a = Team.query.get(match.team_a_id)
                team_b = Team.query.get(match.team_b_id)
                
                if team_a and team_b:
                    match_time = match.match_datetime.strftime("%A, %B %d at %I:%M %p")
                    
                    reminder_body = f"""Hi!

📅 MATCH REMINDER - Tomorrow!

Your match is scheduled for tomorrow:

Match Details:
- Round: {match.round}
- Time: {match_time}
- Court: {match.court or 'Assigned on arrival'}
- Opponent: {{opponent_name}}

📋 Reminders:
- Arrive 10 minutes early
- Bring your paddle and water
- Submit scores immediately after the match

See you on the court! 🎾

- BD Padel League
"""
                    # Send to Team A
                    team_a_reminder = reminder_body.replace("{opponent_name}", team_b.team_name)
                    if team_a.player1_email:
                        send_email_notification(team_a.player1_email, f"Tomorrow's Match - vs {team_b.team_name}", team_a_reminder)
                    if team_a.player2_email:
                        send_email_notification(team_a.player2_email, f"Tomorrow's Match - vs {team_b.team_name}", team_a_reminder)
                    
                    # Send to Team B
                    team_b_reminder = reminder_body.replace("{opponent_name}", team_a.team_name)
                    if team_b.player1_email:
                        send_email_notification(team_b.player1_email, f"Tomorrow's Match - vs {team_a.team_name}", team_b_reminder)
                    if team_b.player2_email:
                        send_email_notification(team_b.player2_email, f"Tomorrow's Match - vs {team_a.team_name}", team_b_reminder)
                    
                    # Mark reminder as sent
                    match.reminder_sent = True
                    reminders_sent += 1
        
        db.session.commit()
        print(f"[SCHEDULED TASK] Sent {reminders_sent} match reminders")
        return reminders_sent


if __name__ == "__main__":
    # Run both tasks when script is executed
    print("[SCHEDULED TASKS] Starting automated notifications...")
    send_walkover_warnings()
    send_match_reminders()
    print("[SCHEDULED TASKS] Completed!")
