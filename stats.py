from flask import Flask
from flask import Flask, render_template, request, url_for, flash, redirect
from database_functions import *
from stat_functions import *
from vollis_functions import *
from datetime import datetime, date

app = Flask(__name__)
app.config['SECRET_KEY'] = 'b83880e869f054bfc465a6f46125ac715e7286ed25e88537'

@app.context_processor
def all_years():
    all_years = grab_all_years()
    return dict(all_years=all_years)

@app.route('/year/<year>/')
def past_year_games(year):
    past_year_games = year_games(year)
    return render_template('games.html', games=past_year_games, year=year)

@app.route('/')
def index():
    minimum_games = 20
    t_stats = todays_stats()
    stats = stats_per_year(str(date.today().year), minimum_games)
    rare_stats = rare_stats_per_year(str(date.today().year), minimum_games)
    return render_template('stats.html', todays_stats=t_stats, stats=stats, rare_stats=rare_stats, minimum_games=minimum_games, year=str(date.today().year))

@app.route('/stats/<year>/')
def stats(year):
    minimum_games = 20
    stats = stats_per_year(year, minimum_games)
    rare_stats = rare_stats_per_year(year, minimum_games)
    return render_template('stats.html', stats=stats, rare_stats=rare_stats, minimum_games=minimum_games, year=year)

@app.route('/vollis_stats/<year>/')
def vollis_stats(year):
    minimum_games = 2
    stats = vollis_stats_per_year(year, minimum_games)
    rare_stats = rare_vollis_stats_per_year(year, minimum_games)
    return render_template('vollis_stats.html', stats=stats, rare_stats=rare_stats, minimum_games=minimum_games, year=year)

@app.route('/vollis_stats/')
def vollis():
    year = str(date.today().year)
    minimum_games = 0
    stats = vollis_stats_per_year(year, minimum_games)
    rare_stats = rare_vollis_stats_per_year(year, minimum_games)
    return render_template('vollis_stats.html', stats=stats, rare_stats=rare_stats, minimum_games=minimum_games, year=year)

@app.route('/player/<year>/<name>')
def player_stats(year, name):
    minimum_games = 4
    games = games_from_player_by_year(year, name)
    partner_stats = partner_stats_by_year(year, name, games, minimum_games)
    opponent_stats = opponent_stats_by_year(year, name, games, minimum_games)
    rare_partner_stats = rare_partner_stats_by_year(year, name, games, minimum_games)
    rare_opponent_stats = rare_opponent_stats_by_year(year, name, games, minimum_games)
    return render_template('player.html', opponent_stats=opponent_stats, rare_opponent_stats=rare_opponent_stats,
        partner_stats=partner_stats, rare_partner_stats=rare_partner_stats, 
        year=year, player=name, minimum_games=minimum_games)

@app.route('/games/')
def games():
    games = year_games(str(date.today().year))
    year = str(date.today().year)
    return render_template('games.html', games=games, year=year)

@app.route('/add_game/', methods=('GET', 'POST'))
def add_game():
    scores = all_scores()
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
            add_game_stats([datetime.now(), winner1, winner2, loser1, loser2, winner_score, loser_score, datetime.now()])
            return redirect(url_for('add_game'))

    return render_template('add_game.html', players=players, scores=scores)

@app.route('/add_vollis_game/', methods=('GET', 'POST'))
def add_vollis_game():
    games = vollis_year_games(str(date.today().year))
    players = all_vollis_players(games)
    if request.method == 'POST':
        winner = request.form['winner']
        loser = request.form['loser']
        winner_score = request.form['winner_score']
        loser_score = request.form['loser_score']

        if not winner or not loser or not winner_score or not loser_score:
            flash('All fields required!')
        else:
            add_vollis_stats([datetime.now(), winner, loser, winner_score, loser_score, datetime.now()])
            return redirect(url_for('add_vollis_game'))

    return render_template('add_vollis_game.html', players=players)

@app.route('/edit_games/')
def edit_games():
    games = year_games(str(date.today().year))
    return render_template('edit_games.html', games=games, year=str(date.today().year))

@app.route('/edit_vollis_games/')
def edit_vollis_games():
    games = vollis_year_games(str(date.today().year))
    return render_template('edit_vollis_games.html', games=games, year=str(date.today().year))

@app.route('/edit/<int:id>/',methods = ['GET','POST'])
def update(id):
    game_id = id
    x = find_game(id)
    game = [x[0][0], x[0][1], x[0][2], x[0][3], x[0][4], x[0][5], x[0][6], x[0][7], x[0][8]]
    scores = all_scores()
    games = year_games(str(date.today().year))
    players = all_players(games)
    if request.method == 'POST':
        game_date = request.form['game_date']
        winner1 = request.form['winner1']
        winner2 = request.form['winner2']
        loser1 = request.form['loser1']
        loser2 = request.form['loser2']
        winner_score = request.form['winner_score']
        loser_score = request.form['loser_score']

        if not winner1 or not winner2 or not loser1 or not loser2 or not winner_score or not loser_score:
            flash('All fields required!')
        else:
            update_game(game_id, game_date, winner1, winner2, winner_score, loser1, loser2, loser_score, datetime.now(), game_id)
            return redirect(url_for('edit_games'))
 
    return render_template('edit_game.html', game=game, players=players, scores=scores, year=str(date.today().year))

@app.route('/delete/<int:id>/',methods = ['GET','POST'])
def delete_game(id):
    game_id = id
    game = find_game(id)
    if request.method == 'POST':
        remove_game(game_id)
        return redirect(url_for('edit_games'))
 
    return render_template('delete_game.html', game=game)



