// Search the full roster; keep recent-player order within each matching group.
function rankPlayerSuggestions(players, query) {
    const text = (query || '').trim().toLowerCase();
    if (!text) return players;
    const starts = [], contains = [];
    players.forEach(player => {
        const name = player.toLowerCase();
        if (name.startsWith(text)) starts.push(player);
        else if (name.includes(text)) contains.push(player);
    });
    return starts.concat(contains);
}
