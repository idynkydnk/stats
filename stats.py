from flask import Flask
from flask import Flask, render_template, request, url_for, flash, redirect
from sheets_scrape import *
from datetime import datetime, date

app = Flask(__name__)
app.config['SECRET_KEY'] = 'b83880e869f054bfc465a6f46125ac715e7286ed25e88537'

@app.route('/add/<int:n1>/<int:n2>/')
def add(n1, n2):
    return '<h1>{}</h1>'.format(n1 + n2)

@app.route('/year/<year>/')
def past_year_games(year):
    past_year_games = year_games(year)
    return render_template('games.html', games=past_year_games)

@app.route('/')
def index():
    stats = stats_per_year(str(date.today().year))
    return render_template('stats.html', stats=stats)

@app.route('/stats/<year>/')
def stats(year):
    stats = stats_per_year(year)
    return render_template('stats.html', stats=stats)

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


        if not winner1:
            flash('All fields required!')
        else:
            games.append([date, winner1, winner2, loser1, loser2, winner_score, loser_score])
            return redirect(url_for('index1'))

    return render_template('add_game.html')

