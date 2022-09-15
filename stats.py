from flask import Flask
from flask import Flask, render_template, request, url_for, flash, redirect
from sheets_scrape import *

app = Flask(__name__)

@app.route('/about/')
def about():
    return '<h3>This is a Flask web application.</h3>'

@app.route('/capitalize/<word>/')
def capitalize(word):
    return '<h1>{}</h1>'.format(escape(word.capitalize()))

@app.route('/add/<int:n1>/<int:n2>/')
def add(n1, n2):
    return '<h1>{}</h1>'.format(n1 + n2)

@app.route('/users/<int:user_id>/')
def greet_user(user_id):
   users = ['Bob', 'Jane', 'Adam']
   try:
      return '<h2>Hi {}</h2>'.format(users[user_id])
   except IndexError:
      abort(404)
   return '<h2>Hi {}</h2>'.format(users[user_id])



app.config['SECRET_KEY'] = 'b83880e869f054bfc465a6f46125ac715e7286ed25e88537'

messages = [{'title': 'Message One',
             'content': 'Message One Content'},
            {'title': 'Message Two',
             'content': 'Message Two Content'}
            ]

games = [['9/20/22', 'Kyle Thomson', 'Chris Dedo', 'Justin Chow', 'Brian Fung', 21, 12],
            ['9/12/22', 'Kyle Thomson', 'Chris Dedo', 'Brian Oneill', 'Chris Gregory', 21, 16]]

@app.route('/')
def index():
    return render_template('index.html', messages=messages)

@app.route('/index1')
def index1():
    return render_template('index1.html', games=games)

@app.route('/stats/')
def stats():
    stats = all_player_stats()
    return render_template('stats.html', stats=stats)


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

