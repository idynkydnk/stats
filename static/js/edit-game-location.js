(() => {
    const wrap = document.querySelector('.game-location');
    if (!wrap) return;
    const field = wrap.querySelector('input');
    const list = wrap.querySelector('.autocomplete-list');
    const locations = JSON.parse(wrap.dataset.locations);
    const updateClear = () => wrap.classList.toggle('empty', !field.value.trim());
    function show(items) {
        document.querySelectorAll('.autocomplete-list').forEach(other => {
            if (other !== list) other.style.display = 'none';
        });
        list.replaceChildren();
        items.forEach(location => {
            const option = document.createElement('div');
            option.textContent = location;
            option.addEventListener('click', () => {
                field.value = location;
                list.style.display = 'none';
                field.dispatchEvent(new Event('change', {bubbles: true}));
            });
            list.appendChild(option);
        });
        list.style.display = items.length ? 'block' : 'none';
        list.scrollTop = 0;
    }
    field.addEventListener('focus', () => show(locations));
    field.addEventListener('input', () => {
        const query = field.value.trim().toLowerCase();
        show(query ? locations.filter(location => location.toLowerCase().includes(query)) : []);
        updateClear();
    });
    field.addEventListener('change', updateClear);
    wrap.querySelector('.clear-field-btn').addEventListener('click', event => {
        event.preventDefault();
        field.value = '';
        list.style.display = 'none';
        updateClear();
        field.blur();
    });
    document.addEventListener('click', event => {
        if (!wrap.contains(event.target)) list.style.display = 'none';
    });
    updateClear();
})();
