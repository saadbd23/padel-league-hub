
from app import app, db
from models import Player, Match, Team

def reset_and_recalculate_player_stats():
    """Reset all player stats to zero, then recalculate from completed verified matches only"""
    
    with app.app_context():
        print("Starting player stats reset and recalculation...")
        
        # Step 1: Reset all player stats to zero
        print("\n1. Resetting all player stats to zero...")
        all_players = Player.query.all()
        for player in all_players:
            player.matches_played = 0
            player.wins = 0
            player.losses = 0
            player.draws = 0
            player.points = 0
            player.sets_for = 0
            player.sets_against = 0
            player.games_for = 0
            player.games_against = 0
        
        db.session.commit()
        print(f"   ✓ Reset stats for {len(all_players)} players")
        
        # Step 2: Get all completed and verified matches
        print("\n2. Finding completed and verified matches...")
        completed_matches = Match.query.filter_by(
            status="completed",
            verified=True
        ).all()
        
        print(f"   ✓ Found {len(completed_matches)} completed and verified matches")
        
        # Step 3: Recalculate stats for each match
        print("\n3. Recalculating player stats from verified matches...")
        
        for match in completed_matches:
            team_a = Team.query.get(match.team_a_id)
            team_b = Team.query.get(match.team_b_id)
            
            if not team_a or not team_b:
                print(f"   ⚠ Skipping match {match.id}: Missing team data")
                continue
            
            print(f"\n   Processing Match {match.id}: {team_a.team_name} vs {team_b.team_name}")
            print(f"   Score: {match.score_a} (Winner: {'Team A' if match.winner_id == team_a.id else 'Team B' if match.winner_id == team_b.id else 'Draw'})")
            
            # Get players who actually participated in this match
            players_a = []
            players_b = []
            
            # Team A players (using match-specific player IDs if available)
            if match.team_a_player1_id:
                player1_a = Player.query.get(match.team_a_player1_id)
                if player1_a:
                    players_a.append(player1_a)
                    print(f"   - Team A Player 1: {player1_a.name}")
            
            if match.team_a_player2_id and match.team_a_player2_id != match.team_a_player1_id:
                player2_a = Player.query.get(match.team_a_player2_id)
                if player2_a:
                    players_a.append(player2_a)
                    print(f"   - Team A Player 2: {player2_a.name}")
            
            # Team B players (using match-specific player IDs if available)
            if match.team_b_player1_id:
                player1_b = Player.query.get(match.team_b_player1_id)
                if player1_b:
                    players_b.append(player1_b)
                    print(f"   - Team B Player 1: {player1_b.name}")
            
            if match.team_b_player2_id and match.team_b_player2_id != match.team_b_player1_id:
                player2_b = Player.query.get(match.team_b_player2_id)
                if player2_b:
                    players_b.append(player2_b)
                    print(f"   - Team B Player 2: {player2_b.name}")
            
            # If no match-specific players, fall back to team roster
            if not players_a:
                print(f"   ⚠ No match-specific players for Team A, using team roster")
                player1_a = Player.query.filter_by(phone=team_a.player1_phone).first()
                if player1_a:
                    players_a.append(player1_a)
                if team_a.player2_phone != team_a.player1_phone:
                    player2_a = Player.query.filter_by(phone=team_a.player2_phone).first()
                    if player2_a:
                        players_a.append(player2_a)
            
            if not players_b:
                print(f"   ⚠ No match-specific players for Team B, using team roster")
                player1_b = Player.query.filter_by(phone=team_b.player1_phone).first()
                if player1_b:
                    players_b.append(player1_b)
                if team_b.player2_phone != team_b.player1_phone:
                    player2_b = Player.query.filter_by(phone=team_b.player2_phone).first()
                    if player2_b:
                        players_b.append(player2_b)
            
            # Update stats for Team A players
            for player in players_a:
                player.matches_played += 1
                player.sets_for += match.sets_a
                player.sets_against += match.sets_b
                player.games_for += match.games_a
                player.games_against += match.games_b
                
                if match.winner_id == team_a.id:
                    player.wins += 1
                    player.points += 3
                elif match.winner_id == team_b.id:
                    player.losses += 1
                else:
                    player.draws += 1
                    player.points += 1
                
                print(f"     ✓ Updated {player.name}: {player.matches_played} matches, {player.points} points")
            
            # Update stats for Team B players
            for player in players_b:
                player.matches_played += 1
                player.sets_for += match.sets_b
                player.sets_against += match.sets_a
                player.games_for += match.games_b
                player.games_against += match.games_a
                
                if match.winner_id == team_b.id:
                    player.wins += 1
                    player.points += 3
                elif match.winner_id == team_a.id:
                    player.losses += 1
                else:
                    player.draws += 1
                    player.points += 1
                
                print(f"     ✓ Updated {player.name}: {player.matches_played} matches, {player.points} points")
        
        # Commit all changes
        db.session.commit()
        
        # Step 4: Display final results
        print("\n" + "="*60)
        print("FINAL PLAYER STATS (Players with matches only):")
        print("="*60)
        
        active_players = Player.query.filter(Player.matches_played > 0).order_by(
            Player.points.desc(),
            Player.wins.desc(),
            Player.matches_played.desc()
        ).all()
        
        for idx, player in enumerate(active_players, 1):
            win_pct = (player.wins / player.matches_played * 100) if player.matches_played > 0 else 0
            print(f"\n{idx}. {player.name}")
            print(f"   Record: {player.wins}-{player.losses}-{player.draws} ({win_pct:.1f}% wins)")
            print(f"   Points: {player.points}")
            print(f"   Sets: {player.sets_for}-{player.sets_against} (diff: {player.sets_diff:+d})")
            print(f"   Games: {player.games_for}-{player.games_against} (diff: {player.games_diff:+d})")
        
        print("\n" + "="*60)
        print(f"✓ Successfully recalculated stats for {len(active_players)} active players")
        print("="*60)

if __name__ == "__main__":
    reset_and_recalculate_player_stats()
