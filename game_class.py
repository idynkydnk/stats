from datetime import datetime
import time

class doubles_game:
    def __init__(self, winner1, winner2, winner_score, loser1, loser2, loser_score, game_datetime = None, last_mod_datetime = None, game_id = None):
        self.game_id = game_id
        if isinstance(game_datetime, datetime):
            self.game_datetime = game_datetime
        else:
            self.game_datetime = doubles_game.str2datetime(game_datetime) if game_datetime else None
        self.winner1 = winner1
        self.winner2 = winner2
        self.winner_score = winner_score
        self.loser1 = loser1
        self.loser2 = loser2
        self.loser_score = loser_score
        
        if isinstance(last_mod_datetime, datetime):
            self.last_mod_datetime = last_mod_datetime
        else:
            self.last_mod_datetime = doubles_game.str2datetime(last_mod_datetime) if last_mod_datetime else None
        
    @staticmethod
    def db_row2doubles_game(row):
        return doubles_game(row[2], row[3], row[4], row[5], row[6], row[7], game_id=row[0], game_datetime=row[1], last_mod_datetime=row[8])
    
    def convert2db_row(self):
        return (self.game_id, str(self.game_datetime), self.winner1, self.winner2, self.winner_score, self.loser1, self.loser2, self.loser_score, str(self.last_mod_datetime))
    
    def __str__(self):
        out_str = ''
        for attr in dir(self):
            # Getting rid of dunder methods
            if not attr.startswith("__"):
                out_str  = out_str + attr + ": " + str(getattr(self, attr)) + "\n"
        return str
    
    @staticmethod
    def str2datetime(txt):
        return datetime.strptime(txt, "%Y-%m-%d %H:%M:%S.%f")
    @staticmethod
    def datetime2str(d):
        return d.strftime("%m/%d/%Y %I:%M %p")
    
    def utc2local(utc):
        epoch = time.mktime(utc.timetuple())
        offset = datetime.fromtimestamp(epoch) - datetime.utcfromtimestamp(epoch)
        return utc + offset