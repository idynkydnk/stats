# Execute this script to run the flask app locally
# running "flask --app stats run --debug" on the python interpreter will do the same thing
from stats import *
import time


if __name__ == '__main__':

   # st = time.process_time() # get the start time   
   # games = games_for_year('Past Year')
   # stats = adv_stats(games)
   # et = time.process_time() # get the end timed
   # # get execution time
   # print('CPU Execution time:', et - st, 'seconds')

   # for player_stats in stats:
   #    print(list(player_stats.values()))

   app.run(debug = True)