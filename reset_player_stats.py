
<old_str>"""
Reset and recalculate ALL player statistics from scratch
This ensures player stats are accurate based on their actual match participation
"""
from app import app, db
from models import Player, Match, Team

def reset_and_recalculate_player_stats():
    with app.app_context():
        print("🔄 Resetting ALL player statistics...")
        
        # Reset all player stats to 0
        players = Player.query.all()
        for player in players:
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
        print(f"✓ Reset {len(players)} player records")
        
        # Recalculate from all completed matches
        completed_matches = Match.query.filter_by(status="completed").all()
        print(f"\n📊 Recalculating from {len(completed_matches)} completed matches...")
        
        for match in completed_matches:
            team_a = Team.query.get(match.team_a_id)
            team_b = Team.query.get(match.team_b_id)
            
            if not team_a or not team_b:
                continue
            
            print(f"\n  Match {match.id}: {team_a.team_name} vs {team_b.team_name}")
            
            # Get Team A players
            players_a = []
            player1_a = Player.query.filter_by(phone=team_a.player1_phone).first()
            if player1_a:
                players_a.append(player1_a)
            
            if team_a.player2_phone != team_a.player1_phone:
                player2_a = Player.query.filter_by(phone=team_a.player2_phone).first()
                if player2_a:
                    players_a.append(player2_a)
            
            # Get Team B players
            players_b = []
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
        
        db.session.commit()
        print("\n✅ Player stats recalculation complete!")
        
        # Show summary
        print("\n📊 Final Player Stats Summary:")
        all_players = Player.query.filter(Player.matches_played > 0).order_by(
            Player.points.desc(),
            Player.wins.desc()
        ).all()
        
        for idx, player in enumerate(all_players, 1):
            print(f"{idx}. {player.name}: {player.matches_played} matches, {player.points} pts, {player.wins}W-{player.draws}D-{player.losses}L")

if __name__ == "__main__":
    reset_and_recalculate_player_stats()</old_str>
<new_str>"""
Reset and recalculate ALL player statistics from scratch
This ensures player stats are accurate based on their actual match participation
FIXED: Now properly includes BOTH winners AND losers in player leaderboard
"""
from app import app, db
from models import Player, Match, Team
from datetime import datetime

def reset_and_recalculate_player_stats():
    with app.app_context():
        print("🔄 Resetting ALL player statistics...")
        
        # Reset all player stats to 0
        players = Player.query.all()
        for player in players:
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
        print(f"✓ Reset {len(players)} player records")
        
        # Recalculate from all completed matches
        completed_matches = Match.query.filter_by(status="completed", verified=True).all()
        print(f"\n📊 Recalculating from {len(completed_matches)} completed matches...")
        
        for match in completed_matches:
            team_a = Team.query.get(match.team_a_id)
            team_b = Team.query.get(match.team_b_id)
            
            if not team_a or not team_b:
                print(f"  ⚠️ Skipping Match {match.id}: Missing team data")
                continue
            
            print(f"\n  Match {match.id} (Round {match.round}): {team_a.team_name} vs {team_b.team_name}")
            print(f"    Score: {match.score_a} | Winner: {team_a.team_name if match.winner_id == team_a.id else team_b.team_name if match.winner_id == team_b.id else 'Draw'}")
            
            # Get or create Team A players
            players_a = []
            player1_a = Player.query.filter_by(phone=team_a.player1_phone).first()
            if not player1_a:
                player1_a = Player(
                    name=team_a.player1_name,
                    phone=team_a.player1_phone,
                    email=team_a.player1_email,
                    current_team_id=team_a.id,
                    created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )
                db.session.add(player1_a)
                db.session.flush()
                print(f"    ➕ Created player: {player1_a.name}")
            players_a.append(player1_a)
            
            if team_a.player2_phone != team_a.player1_phone:
                player2_a = Player.query.filter_by(phone=team_a.player2_phone).first()
                if not player2_a:
                    player2_a = Player(
                        name=team_a.player2_name,
                        phone=team_a.player2_phone,
                        email=team_a.player2_email,
                        current_team_id=team_a.id,
                        created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    )
                    db.session.add(player2_a)
                    db.session.flush()
                    print(f"    ➕ Created player: {player2_a.name}")
                players_a.append(player2_a)
            
            # Get or create Team B players
            players_b = []
            player1_b = Player.query.filter_by(phone=team_b.player1_phone).first()
            if not player1_b:
                player1_b = Player(
                    name=team_b.player1_name,
                    phone=team_b.player1_phone,
                    email=team_b.player1_email,
                    current_team_id=team_b.id,
                    created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )
                db.session.add(player1_b)
                db.session.flush()
                print(f"    ➕ Created player: {player1_b.name}")
            players_b.append(player1_b)
            
            if team_b.player2_phone != team_b.player1_phone:
                player2_b = Player.query.filter_by(phone=team_b.player2_phone).first()
                if not player2_b:
                    player2_b = Player(
                        name=team_b.player2_name,
                        phone=team_b.player2_phone,
                        email=team_b.player2_email,
                        current_team_id=team_b.id,
                        created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    )
                    db.session.add(player2_b)
                    db.session.flush()
                    print(f"    ➕ Created player: {player2_b.name}")
                players_b.append(player2_b)
            
            # Update stats for Team A players (winners OR losers)
            for player in players_a:
                player.matches_played += 1
                player.sets_for += match.sets_a
                player.sets_against += match.sets_b
                player.games_for += match.games_a
                player.games_against += match.games_b
                
                if match.winner_id == team_a.id:
                    player.wins += 1
                    player.points += 3
                    result = "WIN"
                elif match.winner_id == team_b.id:
                    player.losses += 1
                    result = "LOSS"
                else:
                    player.draws += 1
                    player.points += 1
                    result = "DRAW"
                
                print(f"     ✓ {player.name} ({team_a.team_name}): {result} | {player.matches_played} matches, {player.points} pts")
            
            # Update stats for Team B players (winners OR losers)
            for player in players_b:
                player.matches_played += 1
                player.sets_for += match.sets_b
                player.sets_against += match.sets_a
                player.games_for += match.games_b
                player.games_against += match.games_a
                
                if match.winner_id == team_b.id:
                    player.wins += 1
                    player.points += 3
                    result = "WIN"
                elif match.winner_id == team_a.id:
                    player.losses += 1
                    result = "LOSS"
                else:
                    player.draws += 1
                    player.points += 1
                    result = "DRAW"
                
                print(f"     ✓ {player.name} ({team_b.team_name}): {result} | {player.matches_played} matches, {player.points} pts")
        
        db.session.commit()
        print("\n✅ Player stats recalculation complete!")
        
        # Show summary
        print("\n📊 Final Player Stats Summary:")
        all_players = Player.query.filter(Player.matches_played > 0).order_by(
            Player.points.desc(),
            Player.wins.desc(),
            Player.matches_played.desc()
        ).all()
        
        print(f"\nTotal players with match stats: {len(all_players)}")
        for idx, player in enumerate(all_players, 1):
            team = Team.query.get(player.current_team_id) if player.current_team_id else None
            team_name = team.team_name if team else "No team"
            print(f"{idx}. {player.name} ({team_name}): {player.matches_played} matches, {player.points} pts, {player.wins}W-{player.draws}D-{player.losses}L")

if __name__ == "__main__":
    reset_and_recalculate_player_stats()</new_str>
