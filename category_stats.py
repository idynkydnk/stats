"""Combined category results, using the same account/date/location scope as browsing."""
from contextlib import closing
import sqlite3

from other_game_categories import canonical_other_category
from private_accounts import connect_data
from stats_location_filter import filter_stats_connection


def category_results(path, category, year='All years', player=''):
    from other_functions import total_game_name_stats
    category = canonical_other_category(category.strip())
    games, years = [], set()
    tables = ['other_games'] + (['games', 'vollis_games'] if category.casefold() == 'volleyball' else [])
    with closing(connect_data(path)) as conn:
        conn.row_factory = sqlite3.Row
        for table in tables:
            filter_stats_connection(conn, table)
            for record in conn.execute(f'SELECT * FROM {table}'):
                game = dict(record)
                if table == 'other_games':
                    if str(canonical_other_category(game.get('game_type') or '')).casefold() != category.casefold():
                        continue
                else:
                    game['game_name'] = 'Doubles' if table == 'games' else '1v1'
                    if table == 'vollis_games':
                        game['winner1'], game['loser1'] = game.get('winner'), game.get('loser')
                game['source'] = table
                game['winners'] = [game[f'winner{i}'] for i in range(1, 16) if game.get(f'winner{i}')]
                game['losers'] = [game[f'loser{i}'] for i in range(1, 16) if game.get(f'loser{i}')]
                if player and player not in game['winners'] + game['losers']:
                    continue
                game_year = str(game.get('game_date') or '')[:4]
                if game_year:
                    years.add(game_year)
                if year == 'All years' or game_year == str(year):
                    games.append(game)
    games.sort(key=lambda g: str(g.get('game_date') or ''), reverse=True)
    stats = total_game_name_stats(games)
    if player:
        stats = [row for row in stats if row[0] == player]
    return dict(category=category, year=year, all_years=sorted(years, reverse=True) + ['All years'],
                games=games, stats=stats, total_games=len(games), player=player)
