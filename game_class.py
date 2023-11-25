from datetime import datetime, date

class doubles_game:
    def __init__(self, winner1, winner2, winner_score, loser1, loser2, loser_score, game_datetime = None, last_mod_datetime = None, game_id = None):
        self.game_id = game_id
        self.game_datetime = game_datetime
        self.winner1 = winner1
        self.winner2 = winner2
        self.winner_score = winner_score
        self.loser1 = loser1
        self.loser2 = loser2
        self.loser_score = loser_score
        
        self.last_mod_datetime = last_mod_datetime

    @staticmethod
    def db_row2doubles_game(row):
        if len(row[1]) > 19:
            row_datetime = datetime.strptime(row[1], "%Y-%m-%d %H:%M:%S.%f")
            row_date = row_datetime.strftime("%m/%d/%Y %I:%M %p")
        else:
            row_datetime = datetime.strptime(row[1], "%Y-%m-%d %H:%M:%S")
            row_date = row_datetime.strftime("%m/%d/%Y")
        if len(row[8]) > 19:
            updated_datetime = datetime.strptime(row[8], "%Y-%m-%d %H:%M:%S.%f")
            updated_date = updated_datetime.strftime("%m/%d/%Y %I:%M %p")
        else:
            updated_datetime = datetime.strptime(row[8], "%Y-%m-%d %H:%M:%S")
            updated_date = updated_datetime.strftime("%m/%d/%Y")

        return doubles_game(row[2], row[3], row[4], row[5], row[6], row[7], game_id=row[0], game_datetime=row_date, last_mod_datetime=updated_date)
    
    def convert2db_row(self):
        return (self.game_id, self.game_datetime, self.winner1, self.winner2, self.winner_score, self.loser1, self.loser2, self.loser_score, self.last_mod_datetime)
    
    def __str__(self):
        out_str = ''
        for attr in dir(self):
            # Getting rid of dunder methods
            if not attr.startswith("__"):
                out_str  = out_str + attr + ": " + str(getattr(self, attr)) + "\n"
        return str