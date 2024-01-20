from datetime import datetime

class doubles_game:
    def __init__(self, winner1, winner2, winner_score, loser1, loser2, loser_score, game_datetime = None, last_mod_datetime = None, game_id = None, privacy_mode = False):
        self.privacy_mode = privacy_mode

        # Store players names so the winners and losers are in alphabetic order
        if winner1 < winner2:
            self._players = [winner1, winner2]
        else:
            self._players = [winner2, winner1]
        if loser1 < loser2:
            self._players += [loser1, loser2]
        else:
            self._players += [loser2, loser1]

        self.game_id = game_id
        if isinstance(game_datetime, datetime):
            self.game_datetime = game_datetime
        else:
            self.game_datetime = doubles_game.str2datetime(game_datetime) if game_datetime else None

        self.winner_score = winner_score
        self.loser_score = loser_score
        
        if isinstance(last_mod_datetime, datetime):
            self.last_mod_datetime = last_mod_datetime
        else:
            self.last_mod_datetime = doubles_game.str2datetime(last_mod_datetime) if last_mod_datetime else None
        
    @property 
    def players(self):
        if self.privacy_mode:
            return [doubles_game.privacy_mask(x) for x in self._players]
        return self._players
    @property 
    def winners(self):
        if self.privacy_mode:
            return [doubles_game.privacy_mask(x) for x in self._players[0:2]]
        return self._players[0:2]
    @property 
    def losers(self):
        if self.privacy_mode:
            return [doubles_game.privacy_mask(x) for x in self._players[2:4]]
        return self._players[2:4]
    
    @staticmethod
    def db_row2doubles_game(row):
    # Converts a row of data from the database into a doubles_game object
        return doubles_game(row[2], row[3], row[4], row[5], row[6], row[7], game_id=row[0], game_datetime=row[1], last_mod_datetime=row[8])
    
    def convert2db_row(self):
    # Converts a doubles_game object into a row of data for the database
        return (self.game_id, str(self.game_datetime)[:19], self.winners[0], self.winners[1], self.winner_score, self.losers[0], self.losers[1], self.loser_score, str(self.last_mod_datetime)[:19])
    
    def __str__(self):
        out_str = ''
        for attr in dir(self):
            # Getting rid of dunder methods
            if not attr.startswith("__"):
                out_str  = out_str + attr + ": " + str(getattr(self, attr)) + "\n"
        return str
    
    @staticmethod
    def str2datetime(txt):
        if len(txt) > 19: # [ToDo] Don't think this branch will be required if i clean up old entries in the DB and don't store decimal place ms
            txt = txt[:19]
        return datetime.strptime(txt, "%Y-%m-%d %H:%M:%S")
    @staticmethod
    def datetime2str(d):
        return d.strftime("%m/%d/%Y %I:%M %p")
    
    @staticmethod
    def privacy_mask(name):
        parts = name.split()
        if len(parts) < 2:
            return name
        return parts[0] + " " + parts[1][0] # 1st name plus 1st letter of last name