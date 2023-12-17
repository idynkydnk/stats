function SwapElementValues(el1_id, el2_id){
    // Swaps the value properties of two elements specified by their IDs
        var tmp = document.getElementById(el1_id).value;
        document.getElementById(el1_id).value = document.getElementById(el2_id).value;
        document.getElementById(el2_id).value = tmp;
    }
    function SwapWinnersAndLosers() {
        SwapElementValues('w1', 'l1');
        SwapElementValues('w2', 'l2');
    }
    function SortFields(){
    // Updates fields by putting the team members in alphabetic order
        const w1 = document.getElementById('w1').value;
        const w2 = document.getElementById('w2').value;
        if (w1.localeCompare(w2) > 0){
            SwapElementValues('w1', 'w2');
        }
        const l1 = document.getElementById('l1').value;
        const l2 = document.getElementById('l2').value;
        if (l1.localeCompare(l2) > 0){
            SwapElementValues('l1', 'l2');
        }
    }
    function ShufflePlayers(){
    // Shuffles the team player composition
    // There are 3 unique shuffle orders corresponding to the 3 unique teams that can be formed with 4 players
    // The first player stays fixed in all shuffles and his partner is changed. The 3 possible shuffles are numbered 0 through 3 
    // in alphabetic order of the choices for 2nd player's name (1st players partner).
    // Note that if the shuffle operation is carried out 3 times then one gets back to the original teams
         
        debug = false;

        // get array of player names and keep the last 3 players since the 1st player will stay put in the shuffle
        let player_el = Array.from(document.getElementsByClassName( 'player' )).slice(1,4);
        var player_name = [];
        for (var i = 0; i < player_el.length; i++) {
            player_name[i] = player_el[i].value;
        }
        if (debug) {
            console.log('Initial player order');
            console.log(player_name);
        }
        init_player2 = player_name[0]; //record initial value of 2nd player name
        player_name.sort();
        // figure out which of the 3 possible shuffle orders was the initial state (init_shuffle)
        for (var init_shuffle = 0; init_shuffle < player_name.length; init_shuffle++) {
            if (player_name[init_shuffle] === init_player2) {
                break;
            }
        }
        if (debug) {
            console.log('Sorted player order');
            console.log(player_name);
            console.log('Initial order corresponds to shuffle #' + init_shuffle)
            console.log('Final order corresponds to shuffle #' +  (init_shuffle + 1)%3)
        }

        // Increment the team state to the next shuffle (init_shuffle + 1)
        const field_id = ['w2', 'l1', 'l2'];
        for (var ii = 0; ii < 3; ii++) {
            document.getElementById(field_id[ii]).value = player_name[(init_shuffle + 1 + ii) % 3];
        }
    }