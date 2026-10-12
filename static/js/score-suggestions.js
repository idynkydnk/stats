// Keep common scores for empty fields; search every two-digit score when typing.
function winnerScoreSuggestions(query, defaults) {
    const prefix = (query || '').trim();
    if (!prefix) return defaults;
    const scores = new Set(Array.from({ length: 100 }, (_, score) => String(score)));
    defaults.forEach(score => scores.add(String(score)));
    return Array.from(scores)
        .filter(score => score.startsWith(prefix))
        .sort((a, b) => Number(a) - Number(b));
}
