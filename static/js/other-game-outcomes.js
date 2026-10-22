/* Result is explicit: matching scores alone do not change a game's outcome. */
(function () {
    const result = document.getElementById('is_tie');
    if (!result) return;
    const form = result.closest('form');
    const help = document.getElementById('tie-help');
    const resultField = result.closest('.sr-result-field');
    const gameType = document.getElementById('game_type');
    function updateLabels() {
        result.setCustomValidity('');
        const volleyball = resultField.dataset.oneOnOne === '1' || (gameType.value || '').toLowerCase().includes('volleyball');
        resultField.hidden = volleyball;
        if (volleyball) result.value = '0';
        const tied = result.value === '1';
        help.hidden = !tied;
        ['winner', 'loser'].forEach(function (side, index) {
            const label = tied ? 'Side ' + (index + 1) : (index === 0 ? 'Winner' : 'Loser');
            form.querySelectorAll('input[name^="' + side + '"]').forEach(function (input) {
                const match = input.name.match(/^(winner|loser)(\d+)$/);
                if (match) {
                    input.placeholder = tied ? label + ' player ' + match[2] : label + ' ' + match[2];
                    input.setAttribute('aria-label', input.placeholder);
                } else if (input.name === side + '_score') {
                    input.placeholder = label + (tied ? ' Score' : ' Team Score');
                    input.setAttribute('aria-label', input.placeholder);
                }
                const clear = input.parentElement.querySelector('.clear-field-btn');
                if (clear) {
                    const number = input.name.match(/\d+/);
                    const description = label + (number ? ' player ' + number[0] : '') + (input.name.endsWith('_score') ? ' score' : '');
                    clear.setAttribute('aria-label', 'Clear ' + description.toLowerCase());
                    clear.title = 'Clear ' + description.toLowerCase();
                }
            });
            const add = document.getElementById('add-' + side + '-btn');
            if (add) {
                const text = tied ? '+ Add ' + label + ' Player' : '+ Add ' + label;
                if (add.textContent !== text) add.textContent = text;
            }
        });
    }
    result.addEventListener('change', updateLabels);
    form.addEventListener('input', updateLabels);
    form.addEventListener('change', updateLabels);
    form.addEventListener('click', updateLabels);
    form.addEventListener('submit', function (event) {
        updateLabels();
        if (resultField.hidden || result.value === '1' || document.getElementById('score_type').value !== 'team') return;
        const first = document.getElementById('winner_score').value.trim();
        const second = document.getElementById('loser_score').value.trim();
        if (first !== '' && second !== '' && Number(first) === Number(second)) {
            event.preventDefault();
            result.setCustomValidity('These scores are tied. Choose Tie for the result.');
            result.reportValidity();
        }
    });
    window.updateOtherGameOutcome = updateLabels;
    const clear = document.getElementById('clear-form-btn');
    if (clear) clear.addEventListener('click', function () { result.value = '0'; updateLabels(); });
    new MutationObserver(updateLabels).observe(form, {childList: true, subtree: true});
    updateLabels();
})();
