// Steam Charts-inspired Stats Page JavaScript

document.addEventListener('DOMContentLoaded', function() {
    initSearch();
    initSorting();
    initRatingInfoPopover();
});

// ============================================
// RATING INFO POPOVER
// ============================================
function initRatingInfoPopover() {
    const buttons = document.querySelectorAll('.sr-rating-info-btn');
    if (!buttons.length) return;

    function closeAllPopovers() {
        document.querySelectorAll('.sr-rating-popover').forEach(function(pop) {
            pop.hidden = true;
        });
    }

    function openPopover(popover) {
        closeAllPopovers();
        // Move to body so table/layout cannot constrain width; force 80% viewport
        if (popover.parentNode !== document.body) {
            document.body.appendChild(popover);
        }
        popover.style.position = 'fixed';
        popover.style.left = '10vw';
        popover.style.width = '80vw';
        popover.style.maxWidth = '80vw';
        popover.style.top = '50%';
        popover.style.transform = 'translateY(-50%)';
        popover.style.boxSizing = 'border-box';
        popover.style.whiteSpace = 'normal';
        popover.hidden = false;
    }

    buttons.forEach(function(btn) {
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            const popover = this.parentElement.querySelector('.sr-rating-popover');
            if (!popover) return;
            const isOpen = !popover.hidden;
            if (isOpen) {
                closeAllPopovers();
            } else {
                openPopover(popover);
            }
        });
    });

    document.addEventListener('click', closeAllPopovers);
}

// ============================================
// SEARCH FILTERING
// ============================================
let searchTimeout = null;
let currentSearchQuery = '';

function initSearch() {
    const searchInput = document.getElementById('sr-search');
    if (!searchInput) return;
    
    const filterActive = document.getElementById('sr-filter-active');
    const filterChip = document.getElementById('sr-filter-chip');
    const noResults = document.getElementById('sr-no-results');
    const searchDropdown = document.getElementById('sr-search-dropdown');
    
    // Get all sr-table elements on the page
    const tables = document.querySelectorAll('.sr-table');
    
    searchInput.addEventListener('input', function() {
        const query = this.value.toLowerCase().trim();
        currentSearchQuery = query;
        
        // First, filter the existing tables
        filterAllTables(query, tables, filterActive, filterChip, noResults);
        
        // Then, search all players via API if query is not empty
        if (query) {
            // Debounce API calls
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                searchAllPlayers(query, searchDropdown);
            }, 300);
        } else {
            if (searchDropdown) {
                searchDropdown.style.display = 'none';
            }
        }
    });
    
    // Clear filter on chip close click
    const chipClose = document.getElementById('sr-filter-chip-close');
    if (chipClose) {
        chipClose.addEventListener('click', function() {
            searchInput.value = '';
            currentSearchQuery = '';
            filterAllTables('', tables, filterActive, filterChip, noResults);
            if (searchDropdown) {
                searchDropdown.style.display = 'none';
            }
        });
    }
    
    // Close dropdown when clicking outside
    document.addEventListener('click', function(e) {
        if (searchDropdown && !searchInput.contains(e.target) && !searchDropdown.contains(e.target)) {
            searchDropdown.style.display = 'none';
        }
    });
}

function searchAllPlayers(query, dropdown) {
    if (!dropdown || !query) return;
    
    fetch(`/api/search_all_players?q=${encodeURIComponent(query)}`)
        .then(response => response.json())
        .then(players => {
            if (players.length === 0) {
                dropdown.style.display = 'none';
                return;
            }
            
            // Detect which page we're on to determine default link type
            const isVollisPage = window.location.pathname.includes('/vollis');
            const isOtherPage = window.location.pathname.includes('/other');
            
            // Build dropdown HTML
            let html = '<div class="sr-search-dropdown-header">All Players</div>';
            players.forEach(player => {
                const yearText = player.most_recent_year ? ` (Last played: ${player.most_recent_year})` : '';
                const gameTypes = [];
                if (player.has_doubles) gameTypes.push('Doubles');
                if (player.has_vollis) gameTypes.push('Vollis');
                if (player.has_other) gameTypes.push('Other');
                const gamesText = gameTypes.length > 0 ? ` - ${gameTypes.join(', ')}` : '';
                
                // Default to most recent year or first year they played
                const linkYear = player.most_recent_year || (player.years.length > 0 ? player.years[0] : new Date().getFullYear());
                
                // Determine best link based on current page and player's games
                let linkPath;
                if (isVollisPage && player.has_vollis) {
                    linkPath = `/vollis_player/${linkYear}/${encodeURIComponent(player.name)}/`;
                } else if (isOtherPage && player.has_other) {
                    linkPath = `/other_player/${linkYear}/${encodeURIComponent(player.name)}/`;
                } else if (player.has_doubles) {
                    // Default to doubles if they have doubles games
                    linkPath = `/player/${linkYear}/${encodeURIComponent(player.name)}/`;
                } else if (player.has_vollis) {
                    linkPath = `/vollis_player/${linkYear}/${encodeURIComponent(player.name)}/`;
                } else if (player.has_other) {
                    linkPath = `/other_player/${linkYear}/${encodeURIComponent(player.name)}/`;
                } else {
                    // Fallback to doubles page
                    linkPath = `/player/${linkYear}/${encodeURIComponent(player.name)}/`;
                }
                
                html += `<a href="${linkPath}" class="sr-search-dropdown-item">
                    <div class="sr-search-player-name">${player.name}</div>
                    <div class="sr-search-player-info">${yearText}${gamesText}</div>
                </a>`;
            });
            
            dropdown.innerHTML = html;
            dropdown.style.display = 'block';
        })
        .catch(error => {
            console.error('Search error:', error);
            dropdown.style.display = 'none';
        });
}

function filterAllTables(query, tables, filterActive, filterChip, noResults) {
    let totalVisibleCount = 0;
    
    tables.forEach(table => {
        const tbody = table.querySelector('tbody');
        if (!tbody) return;
        
        const rows = tbody.querySelectorAll('tr');
        
        rows.forEach(row => {
            const playerCell = row.querySelector('.sr-player');
            if (!playerCell) return;
            
            const playerName = playerCell.textContent.toLowerCase();
            const matches = (window.srSearch && window.srSearch.matches)
                ? window.srSearch.matches(playerName, query)
                : (query === '' || playerName.includes(query));
            
            row.style.display = matches ? '' : 'none';
            if (matches) totalVisibleCount++;
        });
    });
    
    // Update filter chip visibility
    if (filterActive && filterChip) {
        if (query) {
            filterActive.classList.add('visible');
            filterChip.querySelector('.sr-filter-text').textContent = `"${query}"`;
        } else {
            filterActive.classList.remove('visible');
        }
    }
    
    // Show/hide no results message
    if (noResults) {
        if (totalVisibleCount === 0 && query) {
            noResults.classList.add('visible');
        } else {
            noResults.classList.remove('visible');
        }
    }
}

// ============================================
// TABLE SORTING
// ============================================
const tableSortState = new WeakMap();

function initSorting() {
    document.querySelectorAll('table').forEach(initTableSorting);
}

function initTableSorting(table) {
    if (!table || table.dataset.sortReady === '1') return;

    const headers = table.querySelectorAll('th[data-sort]');
    if (!headers.length) return;

    table.dataset.sortReady = '1';
    const state = { column: -1, direction: 'desc' };
    tableSortState.set(table, state);

    headers.forEach((header) => {
        header.addEventListener('click', function(e) {
            if (e.target.closest('.sr-rating-info-btn')) return;

            const columnIndex = this.cellIndex;
            const isNumeric = this.classList.contains('sr-numeric');
            const st = tableSortState.get(table);

            if (st.column === columnIndex) {
                st.direction = st.direction === 'asc' ? 'desc' : 'asc';
            } else {
                st.column = columnIndex;
                st.direction = isNumeric ? 'desc' : 'asc';
            }

            sortTable(table, columnIndex, st.direction, isNumeric);
            updateSortIndicators(headers, this, st.direction);
        });
    });

    // Show the default-sort indicator without reordering (keeps server order)
    const defaultKey = table.dataset.defaultSort;
    if (defaultKey) {
        const defaultHeader = table.querySelector('th[data-sort="' + defaultKey + '"]');
        if (defaultHeader) {
            state.column = defaultHeader.cellIndex;
            state.direction = table.dataset.defaultDir || (defaultHeader.classList.contains('sr-numeric') ? 'desc' : 'asc');
            updateSortIndicators(headers, defaultHeader, state.direction);
        }
    }
}

function sortTable(table, columnIndex, direction, isNumeric) {
    const tbody = table.querySelector('tbody');
    if (!tbody) return;

    const rows = Array.from(tbody.querySelectorAll('tr'));
    const wasCollapsed = !!tbody.querySelector('.sr-hidden');
    const collapseLimit = parseInt(table.dataset.collapseLimit || '5', 10);

    rows.sort((a, b) => {
        const aCell = a.cells[columnIndex];
        const bCell = b.cells[columnIndex];
        if (!aCell || !bCell) return 0;

        let aVal = aCell.dataset.value !== undefined ? aCell.dataset.value : aCell.textContent.trim();
        let bVal = bCell.dataset.value !== undefined ? bCell.dataset.value : bCell.textContent.trim();

        if (isNumeric) {
            aVal = parseFloat(aVal);
            bVal = parseFloat(bVal);
            if (isNaN(aVal)) aVal = 0;
            if (isNaN(bVal)) bVal = 0;
            return direction === 'asc' ? aVal - bVal : bVal - aVal;
        }

        aVal = String(aVal).toLowerCase();
        bVal = String(bVal).toLowerCase();
        if (direction === 'asc') {
            return aVal.localeCompare(bVal);
        }
        return bVal.localeCompare(aVal);
    });

    rows.forEach((row, index) => {
        tbody.appendChild(row);

        const rankCell = row.querySelector('.sr-rank');
        if (rankCell) {
            rankCell.textContent = index + 1;
            if (table.classList.contains('sr-table')) {
                rankCell.className = 'sr-rank';
                if (index === 0) rankCell.classList.add('sr-rank-1');
                else if (index === 1) rankCell.classList.add('sr-rank-2');
                else if (index === 2) rankCell.classList.add('sr-rank-3');
            }
        }

        if (wasCollapsed) {
            if (index >= collapseLimit) row.classList.add('sr-hidden');
            else row.classList.remove('sr-hidden');
        }
    });
}

function updateSortIndicators(headers, activeHeader, direction) {
    headers.forEach((header) => {
        const arrow = header.querySelector('.sr-sort-arrow');
        if (!arrow) return;

        if (header === activeHeader) {
            header.classList.add('sr-sorted');
            arrow.textContent = direction === 'asc' ? '▲' : '▼';
        } else {
            header.classList.remove('sr-sorted');
            arrow.textContent = '▼';
        }
    });
}

window.initStatsSorting = initSorting;

function toggleCardRows(tbodyId, btn, limit) {
    const tbody = document.getElementById(tbodyId);
    if (!tbody) return;
    const maxRows = limit || 5;
    const hidden = tbody.querySelectorAll('.sr-hidden');
    if (!btn.dataset.expandLabel) btn.dataset.expandLabel = btn.textContent;
    if (hidden.length > 0) {
        hidden.forEach(row => row.classList.remove('sr-hidden'));
        btn.textContent = 'Show less';
    } else {
        tbody.querySelectorAll('tr').forEach((row, i) => {
            if (i >= maxRows) row.classList.add('sr-hidden');
        });
        btn.textContent = btn.dataset.expandLabel;
    }
}