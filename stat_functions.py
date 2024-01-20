from database_functions import *
from datetime import datetime, date
from trueskill import *


def adv_stats(games):
   """Takes in a list of doubles_game objects and returns advanced stats
   games list is assumed to be sorted in order of oldest to newest game date
   """
   players = all_players(games)

   # create ratings
   env = TrueSkill(draw_probability=0)
   info = {}
   for player in players:
      info[player] = {'rating': env.create_rating(), 'games': 0, 'wins': 0, 'losses': 0, 'differential': 0.0}

   for game in games:
      rating_groups = [(info[game.winners[0]]['rating'], info[game.winners[1]]['rating']), (info[game.losers[0]]['rating'], info[game.losers[1]]['rating'])]
      (info[game.winners[0]]['rating'], info[game.winners[1]]['rating']), (info[game.losers[0]]['rating'], info[game.losers[1]]['rating']) = rate(rating_groups, ranks=[0, 1])

      tmp_score_diff = game.winner_score - game.loser_score
      for loser in game.losers:
         info[loser]['games'] += 1
         info[loser]['losses'] += 1
         info[loser]['differential'] -= tmp_score_diff
      for winner in game.winners:
         info[winner]['games'] += 1
         info[winner]['wins'] += 1
         info[winner]['differential'] += tmp_score_diff

   #ToDo Below seems wasteful. I already had a dictionary of dictionaries above with all the right info and 
   # Now I'm turning the dictionary of dictionaries into a list of dictionaries and augmenting the info in it
   # Maybe there is a way to avoid this?
   # Also some of the metrics like 'wins' are unused currently
   stats = list()
   for player in info.keys():
      mu = round(info[player]['rating'].mu, 2)
      sigma = round(info[player]['rating'].sigma, 2)
      p_rating = round(mu - 3*sigma, 2)
      tot_games = info[player]['games']
      wins = info[player]['wins']
      win_perc = round(100*info[player]['wins'] / tot_games, 0)
      diff_norm = round(info[player]['differential'] / tot_games, 1) # average score differential for player per game
      stats.append({'player':player, 'games':tot_games, 'wins':wins, 'win_perc':win_perc, 'diff_norm':diff_norm, 'mu':mu, 'sigma':sigma, 'rating':p_rating})
   stats.sort(key=lambda x: x['rating'], reverse=True)
   return stats

def stats_per_year(year, minimum_games):
# year - 'All Years' , 'Past Year' or the desired year

   games = games_for_year(year)
   players = all_players(games)
   stats = []
   no_wins = []
   for player in players:
      wins, losses = 0, 0
      for game in games:
         if player in game.winners:
            wins += 1
         elif player in game.losers:
            losses += 1
      win_percentage = wins / (wins + losses)
      if wins + losses >= minimum_games:
         if wins == 0:
            no_wins.append([player, wins, losses, win_percentage])
         else:
            stats.append([player, wins, losses, win_percentage])
   stats.sort(key=lambda x: x[1], reverse=True)
   stats.sort(key=lambda x: x[3], reverse=True)
   no_wins.sort(key=lambda x: x[2])
   for stat in no_wins:
      stats.append(stat)
   return stats

def team_stats(games, minimum_games):
   """Returns stats for teams that played at least <minimum_games> together"""
   team_stats_dic = {}
   # count wins and losses for all teams
   for game in games:
      winner_team_str = ';'.join(game.winners)
      loser_team_str = ';'.join(game.losers)
      # if <winner_team_str> is not one of the keys for <team_stats_dic> initialize
      if winner_team_str not in team_stats_dic:
         team_stats_dic[winner_team_str] = {'wins':0, 'losses':0}
      if loser_team_str not in team_stats_dic:
         team_stats_dic[loser_team_str] = {'wins':0, 'losses':0}
      team_stats_dic[winner_team_str]['wins'] +=1
      team_stats_dic[loser_team_str]['losses'] +=1

   # built list of team stats
   team_stats = []
   for team_str in team_stats_dic.keys():
      wins = team_stats_dic[team_str]['wins']
      games = wins + team_stats_dic[team_str]['losses']
      if games < minimum_games:
         continue
      win_percent = team_stats_dic[team_str]['wins'] / games * 100

      team_stats.append({ 'players':team_str.split(';'), 'games': games, 'wins':wins, 'win_percentage':win_percent})

   team_stats.sort(key=lambda x: x['win_percentage'], reverse=True)

   return team_stats

#[ToDo] This function is unused. Maybe i should delete it?
def teams(games):
   """For a list of doubles_game objects <games> returns a list of unique pairs of players (teams)"""

   # this loop takes advantage of the fact that winners and losers are stored in alphabetic order in doubles_game objects
   all_teams = set()
   for game in games:
      all_teams = all_teams.union([game.winners[0] + ';' + game.winners[1]])
      all_teams = all_teams.union([game.losers[0] + ';' + game.losers[1]])
   teams_list = []
   for team in all_teams:
      teams_list.append(team.split(';'))
   
   # sort teams list in alphabetic order ... probably don't really need to do this
   teams_list = sorted(teams_list, key = lambda x: (x[0], x[1]))

   return teams_list

def todays_stats(games=None):
   """Returns stats for todays games games input is optional"""
   if not games:
      games = db_todays_games()
   players = all_players(games)
   stats = []
   for player in players:
      wins, losses, differential = 0, 0, 0
      for game in games:
         if player in game.winners:
            wins += 1
            differential += (game.winner_score - game.loser_score)
         elif player in game.losers:
            losses += 1
            differential -= (game.winner_score - game.loser_score)
      win_percentage = wins / (wins + losses)
      stats.append([player, wins, losses, win_percentage, differential])
   stats.sort(key=lambda x: x[4], reverse=True)
   stats.sort(key=lambda x: x[3], reverse=True)
   return stats

def db_todays_games():
   """Returns a list of doubles_game objects for games that took place in the last 15 hours"""
   cur = db_get_cursor()[0]
   cur.execute("SELECT * FROM games WHERE game_date > date('now','-15 hours')")
   rows = cur.fetchall()
   rows.sort(reverse=True)
   # think i need the "if rows" at the end in case of empty rows
   games = [doubles_game.db_row2doubles_game(row) for row in rows if rows]
   return games
   
def rare_stats_per_year(year, minimum_games):
# year - 'All Years' , 'Past Year' or the desired year
   games = games_for_year(year)
   players = all_players(games)
   stats = []
   no_wins = []
   for player in players:
      wins, losses = 0, 0
      for game in games:
         if player in game.winners:
            wins += 1
         elif player in game.losers:
            losses += 1
      win_percentage = wins / (wins + losses)
      if wins + losses < minimum_games:
         if wins == 0:
            no_wins.append([player, wins, losses, win_percentage])
         else:
            stats.append([player, wins, losses, win_percentage])
   stats.sort(key=lambda x: x[1], reverse=True)
   stats.sort(key=lambda x: x[3], reverse=True)
   no_wins.sort(key=lambda x: x[2])
   for stat in no_wins:
      stats.append(stat)
   return stats

def all_players(games):
   """returns a set of all players in a list of doubles_game objects <games>"""
   all_players = set()
   for game in games:
      all_players = all_players.union(game.players)
   return all_players

def games_for_year(year = None):
   """return a list of doubles_game objects for <year> ordered from oldest to newest game date 
         year - str or int, if not provided then will return all games. Can also be 'All Years' or 'Past Year'
   """

# [ToDo] [Optimization] The sorts that take place here are largely unnecessary because the games are already ordered in 
#   ascending date order in the  DB and there appears to only be a few games out of order in the table (rows 3,4,5,6). 
#   Not sure if the below queries are guaranteed to return in the order rows show up in database and not sure there is
#   much impact here
   cur = db_get_cursor()[0]
   if not year or year == 'All Years':
      cur.execute("SELECT * FROM games ORDER BY game_date ASC")
   elif year == 'Past Year':
      cur.execute("SELECT * FROM games WHERE game_date > date('now','-1 years') ORDER BY game_date ASC")
   else:
      cur.execute("SELECT * FROM games WHERE strftime('%Y',game_date)=? ORDER BY game_date ASC", (str(year),))

   rows = cur.fetchall()
   games = [doubles_game.db_row2doubles_game(row) for row in rows if rows]
   return games

def year_dropdown_values(player_name = None):
   """Returns the values to use for the years selection dropdown box"""
   years = db_years(player_name)
   if len(years) > 1:
      years.append('All Years')
      years.append('Past Year')
   return years

def all_games_player(name):
   """"Returns a list of doubles_game objects for all games played by player <name>"""
   cur = db_get_cursor()[0]
   cur.execute("SELECT * FROM games WHERE (winner1=? OR winner2=? OR loser1=? OR loser2=?)", (name, name, name, name))
   rows = cur.fetchall()
   games = [doubles_game.db_row2doubles_game(row) for row in rows if rows]
   return games

def find_game(game_id):
   cur = db_get_cursor()[0]
   cur.execute("SELECT * FROM games WHERE id=?", (game_id,))
   row = cur.fetchall()
   if len(row) == 0:
      raise Exception('No game with id = ' + str(game_id))
   elif len(row) == 1:
      return doubles_game.db_row2doubles_game(row[0])
   else:
      raise Exception('At most single row should have been returned. "id" column in database table should have unique values')
   
def games_for_player_by_year(year, name):
# year - can be a str, or int
   cur = db_get_cursor()[0]
   if year == 'All Years':
      cur.execute("SELECT * FROM games WHERE (winner1=? OR winner2=? OR loser1=? OR loser2=?)", (name, name, name, name))
   elif year == 'Past Year':
      cur.execute("SELECT * FROM games WHERE game_date > date('now','-1 years')  AND (winner1=? OR winner2=? OR loser1=? OR loser2=?)", (name, name, name, name))
   else:
      cur.execute("SELECT * FROM games WHERE strftime('%Y',game_date)=? AND (winner1=? OR winner2=? OR loser1=? OR loser2=?)", (str(year), name, name, name, name))
   rows = cur.fetchall()
   games = [doubles_game.db_row2doubles_game(row) for row in rows if rows]
   return games

def partner_stats_by_year(name, games, minimum_games):
   stats = []
   no_wins = []
   if not games:
      return stats
   else:
      players = all_players(games)
      players.remove(name)
      for partner in players:
         wins, losses = 0, 0
         for game in games:
            if name in game.winners:
               if game.winners[0] == partner or game.winners[1] == partner:
                  wins += 1
            if name in game.losers:
               if game.losers[0] == partner or game.losers[1] == partner:
                  losses += 1
         if wins + losses > 0:
            win_percent = wins / (wins + losses)
            total_games = wins + losses
            if total_games >= minimum_games:
               if wins == 0:
                  no_wins.append({'partner':partner, 'wins':wins, 'losses':losses, 'win_percentage':win_percent, 'total_games':total_games})
               else:
                  stats.append({'partner':partner, 'wins':wins, 'losses':losses, 'win_percentage':win_percent, 'total_games':total_games})
      stats.sort(key=lambda x: x['wins'], reverse=True)
      stats.sort(key=lambda x: x['win_percentage'], reverse=True)
      no_wins.sort(key=lambda x: x['losses'])
      for stat in no_wins:
         stats.append(stat)
      return stats

def rare_partner_stats_by_year(name, games, minimum_games):
   stats = []
   no_wins = []
   if not games:
      return stats
   else:
      players = all_players(games)
      players.remove(name)
      for partner in players:
         wins, losses = 0, 0
         for game in games:
            if name in game.winners:
               if game.winners[0] == partner or game.winners[1] == partner:
                  wins += 1
            if name in game.losers:
               if game.losers[0] == partner or game.losers[1] == partner:
                  losses += 1
         if wins + losses > 0:
            win_percent = wins / (wins + losses)
            total_games = wins + losses
            if total_games < minimum_games:
               if wins == 0:
                  no_wins.append({'partner':partner, 'wins':wins, 'losses':losses, 'win_percentage':win_percent, 'total_games':total_games})
               else:
                  stats.append({'partner':partner, 'wins':wins, 'losses':losses, 'win_percentage':win_percent, 'total_games':total_games})
      stats.sort(key=lambda x: x['wins'], reverse=True)
      stats.sort(key=lambda x: x['win_percentage'], reverse=True)
      no_wins.sort(key=lambda x: x['losses'])
      for stat in no_wins:
         stats.append(stat)
      return stats

def opponent_stats_by_year(name, games, minimum_games):
   stats = []
   no_wins = []
   if not games:
      return stats
   else:
      players = all_players(games)
      players.remove(name)
      for opponent in players:
         wins, losses = 0, 0
         for game in games:
            if name in game.winners:
               if opponent in game.losers:
                  wins += 1
            if name in game.losers:
               if opponent in game.winners:
                  losses += 1
         if wins + losses > 0:
            win_percent = wins / (wins + losses)
            total_games = wins + losses
            if total_games >= minimum_games:
               if wins == 0:
                  no_wins.append({'opponent':opponent, 'wins':wins, 'losses':losses, 'win_percentage':win_percent, 'total_games':total_games})
               else:
                  stats.append({'opponent':opponent, 'wins':wins, 'losses':losses, 'win_percentage':win_percent, 'total_games':total_games})
      stats.sort(key=lambda x: x['wins'], reverse=True)
      stats.sort(key=lambda x: x['win_percentage'], reverse=True)
      no_wins.sort(key=lambda x: x['losses'])
      for stat in no_wins:
         stats.append(stat)
      return stats

def rare_opponent_stats_by_year(name, games, minimum_games):
   stats = []
   no_wins = []
   if not games:
      return stats
   else:
      players = all_players(games)
      players.remove(name)
      for opponent in players:
         wins, losses = 0, 0
         for game in games:
            if name in game.winners:
               if opponent in game.losers:
                  wins += 1
            if name in game.losers:
               if opponent in game.winners:
                  losses += 1
         if wins + losses > 0:
            win_percent = wins / (wins + losses)
            total_games = wins + losses
            if total_games < minimum_games:
               if wins == 0:
                  no_wins.append({'opponent':opponent, 'wins':wins, 'losses':losses, 'win_percentage':win_percent, 'total_games':total_games})
               else:
                  stats.append({'opponent':opponent, 'wins':wins, 'losses':losses, 'win_percentage':win_percent, 'total_games':total_games})
      stats.sort(key=lambda x: x['wins'], reverse=True)
      stats.sort(key=lambda x: x['win_percentage'], reverse=True)
      no_wins.sort(key=lambda x: x['losses'])
      for stat in no_wins:
         stats.append(stat)
      return stats

def total_stats(games, player):
   stats = []
   wins, losses = 0, 0
   for game in games:
      if player in game.winners:
         wins += 1
      elif player in game.losers:
         losses += 1
   win_percentage = wins / (wins + losses)
   stats.append([player, wins, losses, win_percentage])
   return stats