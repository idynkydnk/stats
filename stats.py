from flask import Flask, render_template, request, url_for, flash, redirect
from database_functions import *
from stat_functions import *
from datetime import datetime, date

app = Flask('stats')
app.config['SECRET_KEY'] = 'b83880e869f054bfc465a6f46125ac715e7286ed25e88537'

@app.route('/')
def index():
    curr_year_str = str(date.today().year)
    games = year_games(curr_year_str)
    minimum_games = min_games_required(games, 30)
    all_years = grab_all_years()
    t_stats = todays_stats() # get stats for today's games
    games = todays_games()
    stats = stats_per_year(curr_year_str, minimum_games)
    rare_stats = rare_stats_per_year(curr_year_str, minimum_games)
    return render_template('stats.html', todays_stats=t_stats, stats=stats, games=games, rare_stats=rare_stats, 
        minimum_games=minimum_games, year=curr_year_str, all_years=all_years)

@app.route('/stats/<year>/')
def stats(year):
    games = year_games(year)
    minimum_games = min_games_required(games, 30)
    all_years = grab_all_years()
    stats = stats_per_year(year, minimum_games)
    rare_stats = rare_stats_per_year(year, minimum_games)
    return render_template('stats.html', all_years=all_years, stats=stats, rare_stats=rare_stats, minimum_games=minimum_games, year=year)

@app.route('/top_teams/')
def top_teams():
    all_years = grab_all_years()
    curr_year_str = str(date.today().year)
    games = year_games(curr_year_str)
    minimum_games = min_games_required(games, 70)
    stats = team_stats_per_year(curr_year_str, minimum_games, games)
    return render_template('top_teams.html', all_years=all_years, stats=stats, minimum_games=minimum_games, year=curr_year_str)

@app.route('/top_teams/<year>/')
def top_teams_by_year(year):
    games = year_games(year)
    minimum_games = min_games_required(games, 70)
    all_years = grab_all_years()
    stats = team_stats_per_year(year, minimum_games, games)
    return render_template('top_teams.html', all_years=all_years, stats=stats, minimum_games=minimum_games, year=year)

@app.route('/player/<year>/<name>')
def player_stats(year, name):
    games = games_from_player_by_year(year, name)
    minimum_games = min_games_required(games, 40)
    all_years = all_years_player(name)
    games = games_from_player_by_year(year, name)
    stats = total_stats(games, name)
    partner_stats = partner_stats_by_year(name, games, minimum_games)
    opponent_stats = opponent_stats_by_year(name, games, minimum_games)
    rare_partner_stats = rare_partner_stats_by_year(name, games, minimum_games)
    rare_opponent_stats = rare_opponent_stats_by_year(name, games, minimum_games)
    return render_template('player.html', opponent_stats=opponent_stats, rare_opponent_stats=rare_opponent_stats,
        partner_stats=partner_stats, rare_partner_stats=rare_partner_stats, 
        year=year, player=name, minimum_games=minimum_games, all_years=all_years, stats=stats)

@app.route('/games/')
def games():
    all_years = grab_all_years()
    curr_year_str = str(date.today().year)
    games = year_games(curr_year_str)
    return render_template('games.html', games=games, year=curr_year_str, all_years=all_years)

@app.route('/games/<year>')
def games_by_year(year):
    all_years = grab_all_years()
    games = year_games(year)
    return render_template('games.html', games=games, year=year, all_years=all_years)

@app.route('/add_game/', methods=('GET', 'POST')) # used then making a new game entry from scratch
@app.route('/add_game/<int:game_id>/', methods=('GET', 'POST')) # used then duplicating an old entry to make a new entry
def add_game(game_id = None):

    if game_id: # case when new game entry is a copy of previous game entry 
        x = find_game(game_id)
        game = [x[0][0], x[0][1], x[0][2], x[0][3], x[0][4], x[0][5], x[0][6], x[0][7], x[0][8]]
    else: # new game entry from scratch with only winning score pre-populated
        game = ['','','','','21','','','','']

    games = year_games(str(date.today().year))
    minimum_games = min_games_required(games, 30)
    stats = stats_per_year(str(date.today().year), minimum_games)
    rare_stats = rare_stats_per_year(str(date.today().year), minimum_games)

    games = year_games('All years')
    list_of_all_players = all_players(games)
    t_stats = todays_stats()
    games = todays_games()

    if request.method == 'POST':
        winner1 = request.form['winner1']
        winner2 = request.form['winner2']
        loser1 = request.form['loser1']
        loser2 = request.form['loser2']
        winner_score = request.form['winner_score']
        loser_score = request.form['loser_score']
        game = ['','',winner1, winner2, winner_score, loser1, loser2, loser_score]

        if not winner1 or not winner2 or not loser1 or not loser2 or not winner_score or not loser_score:
            flash('All fields required!')
        elif int(winner_score) < int(loser_score):
            flash('Winner score is less than loser score!')
        elif winner1 == winner2 or winner1 == loser1 or winner1 == loser2 or winner2 == loser1 or winner2 == loser2 or loser1 == loser2:
            flash('Two names are the same!')
        else:
            add_game_stats([datetime.now(), winner1.strip(), winner2.strip(), loser1.strip(), loser2.strip(), 
                winner_score, loser_score, datetime.now()])
            return redirect(url_for('add_game'))
        
    return render_template('add_game.html', todays_stats=t_stats, games=games, players=list_of_all_players, 
                            year=str(date.today().year), stats=stats, rare_stats=rare_stats, minimum_games=minimum_games,
                            game=game)


@app.route('/edit_games/')
def edit_games():
    all_years = grab_all_years()
    games = year_games(str(date.today().year))
    return render_template('edit_games.html', games=games, year=str(date.today().year), all_years=all_years)

@app.route('/edit_games/<year>')
def edit_games_by_year(year):
    all_years = grab_all_years()
    games = year_games(year)
    return render_template('edit_games.html', games=games, year=year, all_years=all_years)


@app.route('/edit/<int:game_id>/',methods = ['GET','POST'])
def update(game_id):
    x = find_game(game_id)
    game = [x[0][0], x[0][1], x[0][2], x[0][3], x[0][4], x[0][5], x[0][6], x[0][7], x[0][8]]
    games = year_games(str(date.today().year))
    players = all_players(games)
    if request.method == 'POST':
        winner1 = request.form['winner1']
        winner2 = request.form['winner2']
        loser1 = request.form['loser1']
        loser2 = request.form['loser2']
        winner_score = request.form['winner_score']
        loser_score = request.form['loser_score']

        if not winner1 or not winner2 or not loser1 or not loser2 or not winner_score or not loser_score:
            flash('All fields required!')
        else:
            update_game(game_id, game[1], winner1, winner2, winner_score, loser1, loser2, loser_score, datetime.now(), game_id)
            return redirect(url_for('edit_games'))
 
    return render_template('edit_game.html', game=game, players=players)


@app.route('/delete/<int:game_id>/',methods = ['GET','POST'])
def delete_game(game_id):
    x = find_game(game_id)
    game = [x[0][0], x[0][1], x[0][2], x[0][3], x[0][4], x[0][5], x[0][6], x[0][7], x[0][8]]
    if request.method == 'POST':
        db_delete_game(game_id)
        return redirect(url_for('edit_games'))
 
    return render_template('delete_game.html', game=game)

@app.route('/advanced_stats/')
def advanced_stats():
    return render_template('advanced_stats.html')

def min_games_required(games, threshold):
    # Min required number of games played to end up in main stats table (people with less end up in lower table)
    if games and len(games) > threshold:
        # people who make up at least 1/30th of the entries get to be in main table
        minimum_games = len(games) // threshold
    else:
        minimum_games = 1
    return minimum_games

#[ToDo] Not sure what this was for. Should probably delete it since it does nothing now.
# Also delete the html file that corresponds to this route
@app.route('/single_game_stats/<game_name>/')
def single_game_stats(game_name):
    all_years = single_game_years(game_name)
    year = str(date.today().year)
    games = single_game_games(year, game_name)
    minimum_games = 0
    stats = total_single_game_stats(games)
    return render_template('single_game_stats.html', stats=stats, game_name=game_name,
        all_years=all_years, minimum_games=minimum_games, year=year)
