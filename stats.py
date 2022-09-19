from flask import Flask
from flask import Flask, render_template, request, url_for, flash, redirect
from database_functions import *
from stat_functions import *
from datetime import datetime, date

app = Flask(__name__)
app.config['SECRET_KEY'] = 'b83880e869f054bfc465a6f46125ac715e7286ed25e88537'

@app.context_processor
def all_years():
    all_years = grab_all_years()
    return dict(all_years=all_years)

@app.route('/add/<int:n1>/<int:n2>/')
def add(n1, n2):
    return '<h1>{}</h1>'.format(n1 + n2)

@app.route('/year/<year>/')
def past_year_games(year):
    past_year_games = year_games(year)
    return render_template('games.html', games=past_year_games)

@app.route('/')
def index():
    minimum_games = 20
    stats = stats_per_year(str(date.today().year), minimum_games)
    rare_stats = rare_stats_per_year(str(date.today().year), minimum_games)
    return render_template('stats.html', stats=stats, rare_stats=rare_stats, minimum_games=minimum_games, year=str(date.today().year))

@app.route('/stats/<year>/')
def stats(year):
    minimum_games = 20
    stats = stats_per_year(year, minimum_games)
    rare_stats = rare_stats_per_year(year, minimum_games)
    return render_template('stats.html', stats=stats, rare_stats=rare_stats, minimum_games=minimum_games, year=year)

@app.route('/games/')
def games():
    games = year_games(str(date.today().year))
    return render_template('games.html', games=games)

@app.route('/create/', methods=('GET', 'POST'))
def create():
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']

        if not title:
            flash('Title is required!')
        elif not content:
            flash('Content is required!')
        else:
            messages.append({'title': title, 'content': content})
            return redirect(url_for('index'))

    return render_template('create.html')

@app.route('/add_game/', methods=('GET', 'POST'))
def add_game():
    if request.method == 'POST':
        date = request.form['date']
        winner1 = request.form['winner1']
        winner2 = request.form['winner2']
        loser1 = request.form['loser1']
        loser2 = request.form['loser2']
        winner_score = request.form['winner_score']
        loser_score = request.form['loser_score']

        if not date or not winner1 or not winner2 or not loser1 or not loser2 or not winner_score or not loser_score:
            flash('All fields required!')
        else:
            add_game_stats([date, winner1, winner2, loser1, loser2, winner_score, loser_score])
            return redirect(url_for('add_game'))

    return render_template('add_game.html')

