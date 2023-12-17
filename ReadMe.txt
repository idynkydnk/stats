* truncate the string for game datetime and last modified datatime to reduce space required in the database
* entries should be stored with team member names in alphabetic order (not a big deal but nice when viewing the database directly)

# I should use straight SQLAlchemy or flask_sqlalchemy to interact with the database instead of sqllite3
# it provides python abstraction for contents of DB and I won't need the doubles_game class potentially ...
- this video illustrates a more correct use of databases or at least flask alchemy ( https://www.youtube.com/watch?v=Z1RJmh_OqeA&t=2448s)

using matplot lib
https://help.pythonanywhere.com/pages/MatplotLibGraphs/



 Drop down box should not offer the player name as an option once the player has been selected in another box
 - players should be sorted by most recently player (already done?)


 Instead of finding unique player names or player combinations using code. Could do it using the SQL query itself.
 - however this may lose the info about returning players in order of most recently player to least recently played

 fix date time being displayed in the wrong timezone (UTC). It's both stored and displayed in that time zone.

 is the games.html page useless ... it probably is suppose to show results for multiple games but i only have on game type (doubles). It's accessible from under the hamburger  menu
 
 switch my repo from public to private and give Kyle access to it.