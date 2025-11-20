
import os
os.environ['DATABASE_URL'] = os.environ.get('DATABASE_URL', 'sqlite:///instance/league.db')

from app import app, db
from models import Team, Match

def reset_and_recalculate_team_stats(team_id):
    """Reset team stats and recalculate from all verified matches"""
    with app.app_context():
        team = Team.query.get(team_id)
        if not team:
            print(f"Team {team_id} not found")
            return

        print(f"\n=== Resetting TEAM LEADERBOARD stats for {team.team_name} (ID: {team_id}) ===")
        print(f"BEFORE RESET:")
        print(f"  Points: {team.points}")
        print(f"  Wins: {team.wins}, Losses: {team.losses}, Draws: {team.draws}")
        print(f"  Matches Played: {team.wins + team.losses + team.draws}")
        print(f"  Sets: {team.sets_for}-{team.sets_against}")
        print(f"  Games: {team.games_for}-{team.games_against}")

        # Reset all team stats to zero
        team.wins = 0
        team.losses = 0
        team.draws = 0
        team.points = 0
        team.sets_for = 0
        team.sets_against = 0
        team.games_for = 0
        team.games_against = 0

        # Get all verified matches where this team participated
        matches = Match.query.filter(
            db.or_(
                Match.team_a_id == team_id,
                Match.team_b_id == team_id
            ),
            Match.verified == True,
            Match.status == 'completed'
        ).all()

        print(f"\nFound {len(matches)} verified completed matches")

        # Mark all matches as NOT calculated to force recalculation
        for match in matches:
            match.stats_calculated = False

        # Recalculate from each match
        for match in matches:
            is_team_a = (match.team_a_id == team_id)

            # Add sets and games
            if is_team_a:
                team.sets_for += match.sets_a
                team.sets_against += match.sets_b
                team.games_for += match.games_a
                team.games_against += match.games_b
            else:
                team.sets_for += match.sets_b
                team.sets_against += match.sets_a
                team.games_for += match.games_b
                team.games_against += match.games_a

            # Add wins/losses/draws and points
            if match.winner_id == team_id:
                team.wins += 1
                team.points += 3
                result = "WIN"
            elif match.winner_id is None:
                team.draws += 1
                team.points += 1
                result = "DRAW"
            else:
                team.losses += 1
                result = "LOSS"

            opponent_id = match.team_b_id if is_team_a else match.team_a_id
            opponent = Team.query.get(opponent_id)
            opponent_name = opponent.team_name if opponent else f"Team {opponent_id}"

            print(f"  Match {match.id} (Round {match.round}): vs {opponent_name} - {result}")
            print(f"    Score: {match.sets_a}-{match.sets_b} (sets), {match.games_a}-{match.games_b} (games)")
            
            # Mark this match as calculated
            match.stats_calculated = True

        # Commit changes
        db.session.commit()

        print(f"\nAFTER RECALCULATION:")
        print(f"  Points: {team.points}")
        print(f"  Wins: {team.wins}, Losses: {team.losses}, Draws: {team.draws}")
        print(f"  Matches Played: {team.wins + team.losses + team.draws}")
        print(f"  Sets: {team.sets_for}-{team.sets_against} (diff: {team.sets_for - team.sets_against:+d})")
        print(f"  Games: {team.games_for}-{team.games_against} (diff: {team.games_for - team.games_against:+d})")
        print(f"\n✅ Team leaderboard stats reset and recalculated successfully!")

if __name__ == "__main__":
    # Reset Apex Legends (team_id = 7)
    reset_and_recalculate_team_stats(7)
