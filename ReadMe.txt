ToDo

* entries should be stored with team member names in alphabetic order (not a big deal but nice when viewing the database directly)

# I should use straight SQLAlchemy or flask_sqlalchemy to interact with the database instead of sqllite3
# it provides python abstraction for contents of DB and I won't need the doubles_game class potentially ...
- this video illustrates a more correct use of databases or at least flask alchemy ( https://www.youtube.com/watch?v=Z1RJmh_OqeA&t=2448s)

using matplot lib
https://help.pythonanywhere.com/pages/MatplotLibGraphs/


 Drop down box should not offer the player name as an option once the player has been selected in another box
 - players should be sorted by most recently player (already done?)


 Instead of finding unique player names or player combinations using code. Could do it using the SQL query itself.
 - however this may lose the info about returning players in order of most recently player to least recently played (is that even happening right now?)
 
 switch my repo from public to private. Don't think this is possible for a fork of a public repo, so i'll have to clone my repo and store is as a separate repo on GitHub

 Facts
 - Prior to 12/17/2023 any datetimes stored in the DB are in UTC and after that date they are in PST. Also truncated the stored string for datatimes to only go down to seconds accuracy