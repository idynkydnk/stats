from flask import Flask, render_template, request, url_for, flash, redirect
from database_functions import *
from stat_functions import *
from datetime import datetime, date
import pytz
from game_class import *

app = Flask('stats')
app.config['SECRET_KEY'] = 'b83880e869f054bfc465a6f46125ac715e7286ed25e88537'

@app.route('/')
@app.route('/stats/<year>/')
def stats(year=None):
    if not year:
        year = 'Past Year'
        todays_games = db_todays_games()
        t_stats = todays_stats(todays_games) # get stats for today's games
    else: # if year was specified
        t_stats = None
        todays_games = None
    
    games = db_games_for_date(year)
    all_years = year_dropdown_values()
    stats = adv_stats(games)
    return render_template('stats.html', todays_stats=t_stats, stats=stats, games=todays_games, 
        year=year, all_years=all_years)

@app.route('/top_teams/')
@app.route('/top_teams/<year>/')
def top_teams_by_year(year = None):
    if not year:
        year = 'Past Year'
    games = db_games_for_date(year)
    minimum_games = min_games_required(games, 30)
    all_years = year_dropdown_values()
    stats = team_stats(games, minimum_games)
    return render_template('top_teams.html', all_years=all_years, stats=stats, minimum_games=minimum_games, year=year)

@app.route('/player/<year>/<name>')
def player_stats(year, name):
    games = games_for_player_by_year(year, name)
    minimum_games = min_games_required(games, 40)
    all_years = year_dropdown_values(name)
    stats = total_stats(games, name)
    partner_stats = partner_stats_by_year(name, games, minimum_games)
    opponent_stats = opponent_stats_by_year(name, games, minimum_games)
    rare_partner_stats = rare_partner_stats_by_year(name, games, minimum_games)
    rare_opponent_stats = rare_opponent_stats_by_year(name, games, minimum_games)
    return render_template('player.html', opponent_stats=opponent_stats, rare_opponent_stats=rare_opponent_stats,
        partner_stats=partner_stats, rare_partner_stats=rare_partner_stats, 
        year=year, player=name, minimum_games=minimum_games, all_years=all_years, stats=stats)

@app.route('/games/')
@app.route('/games/<year>')
def games_by_year(year = None):
    if not year:
        year = 'Past Year'
    all_years = year_dropdown_values()
    games = db_games_for_date(year)
    # Sort most recent to oldest game order
    games.sort(key=lambda x: x.game_datetime, reverse=True)
    return render_template('games.html', games=games, year=year, all_years=all_years)

@app.route('/add_game/', methods=('GET', 'POST')) # used when making a new game entry from scratch
@app.route('/add_game/<int:game_id>/', methods=('GET', 'POST')) # used when duplicating an old entry to add a game
def add_game(game_id = None):

    games = db_games_for_date(date.today().year)
    minimum_games = min_games_required(games, 30)
    stats = stats_per_year('Past Year', minimum_games)
    rare_stats = rare_stats_per_year('Past Year', minimum_games)

    games = db_games_for_date('All Years')
    list_of_all_players = all_players(games)
    games = db_todays_games()
    t_stats = todays_stats(games)
    
    
    if request.method == 'POST':
        winner1 = request.form['winner1'].strip()
        winner2 = request.form['winner2'].strip()
        loser1 = request.form['loser1'].strip()
        loser2 = request.form['loser2'].strip()
        winner_score = request.form['winner_score']
        loser_score = request.form['loser_score']

        game = doubles_game(winner1, winner2, winner_score, loser1, loser2, loser_score, game_datetime = curr_datatime(), last_mod_datetime = curr_datatime())

        if not winner1 or not winner2 or not loser1 or not loser2 or not winner_score or not loser_score:
            flash('All fields required!')
        elif int(winner_score) < int(loser_score):
            flash('Winner score is less than loser score!')
        elif len({winner1, winner2, loser1, loser2}) != 4:
            flash('All player names must be unique')
        else:
            db_add_game(game)
            return redirect(url_for('add_game'))
    else:
        if game_id: # case when new game entry is a copy of previous game entry 
            game = find_game(game_id)
        else: # new game entry from scratch with only winning score pre-populated
            game = doubles_game('','','21','', '', '')
    return render_template('add_game.html', todays_stats=t_stats, games=games, players=list_of_all_players, 
                            year='Past Year', stats=stats, rare_stats=rare_stats, minimum_games=minimum_games,
                            game=game)

@app.route('/edit_games/')
@app.route('/edit_games/<year>')
def edit_games_by_year(year = None):
    if not year:
        year = 'Past Year'

    all_years = year_dropdown_values()
    games = db_games_for_date(year)
    games.sort(key=lambda x: x.game_datetime, reverse=True) # Sort most recent to oldest game order
    return render_template('edit_games.html', games=games, year=year, all_years=all_years)

@app.route('/edit/<int:game_id>/', methods = ['GET','POST'])
def update(game_id):
    
    game = find_game(game_id)
    games = db_games_for_date(date.today().year)
    players = all_players(games)
    
    if request.method == 'POST':
        winner1 = request.form['winner1'].strip()
        winner2 = request.form['winner2'].strip()
        loser1 = request.form['loser1'].strip()
        loser2 = request.form['loser2'].strip()
        winner_score = request.form['winner_score']
        loser_score = request.form['loser_score']

        game = doubles_game(winner1, winner2, winner_score, loser1, loser2, loser_score, game_datetime = game.game_datetime, last_mod_datetime = curr_datatime())
        game.game_id = game_id

        if not winner1 or not winner2 or not loser1 or not loser2 or not winner_score or not loser_score:
            flash('All fields required!')
        elif int(winner_score) < int(loser_score):
            flash('Winner score is less than loser score!')
        elif len({winner1, winner2, loser1, loser2}) != 4:
            flash('All player names must be unique')
        else:
            db_update_game(game)
            return redirect(url_for('edit_games_by_year'))
        
    return render_template('edit_game.html', game=game, players=players)


@app.route('/delete/<int:game_id>/',methods = ['GET','POST'])
def delete_game(game_id):
    game = find_game(game_id)
    if request.method == 'POST':
        db_delete_game(game.game_id)
        return redirect(url_for('edit_games_by_year'))
 
    return render_template('delete_game.html', game=game)

@app.route('/advanced_stats/')
def advanced_stats():
    return render_template('advanced_stats.html')

def min_games_required(games, threshold):
    # Min required number of games played to end up in main stats table
    minimum_games = max(4, len(games) // threshold)
    return minimum_games

def curr_datatime():
# Returns a datetime object with the timezone set to PST
# [ToDo] I suspect this function does nothing useful and the actual format of the conversion from data time to str is determined by a setting for the time zone
# that resides server side in the WSGI file. Test this by replacing the below code by just datetime.now() and confirm that the way data/times are displayed
# on the web site and stored in the database doesn't change ...
    dt_now_pst = datetime.now(pytz.timezone('America/Los_Angeles'))
    return dt_now_pst