// Steam Charts-inspired Stats Page JavaScript

document.addEventListener('DOMContentLoaded', function() {
    try { initSearch(); } catch (e) { console.error(e); }
    try { initSorting(); } catch (e) { console.error(e); }
    try { initRatingInfoPopover(); } catch (e) { console.error(e); }
    try { initPlayerPageSticky(); } catch (e) { console.error(e); }
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

// Player-page win% sorts: ~5% of that player's games (floor 5).
function playerMatchupMinGames(playerGames) {
    if (!playerGames) return 5;
    return Math.max(5, Math.floor(playerGames / 20));
}

function cellNumericValue(row, cellIndex) {
    if (cellIndex < 0 || !row.cells[cellIndex]) return NaN;
    const cell = row.cells[cellIndex];
    const raw = cell.dataset.value !== undefined ? cell.dataset.value : cell.textContent.trim();
    const n = parseFloat(raw);
    return isNaN(n) ? NaN : n;
}

function findSortColumnIndex(table, sortKey) {
    const headers = table.querySelectorAll('th[data-sort]');
    for (let i = 0; i < headers.length; i++) {
        if (headers[i].dataset.sort === sortKey) return headers[i].cellIndex;
    }
    return -1;
}

function isMatchupDataRow(row) {
    return row && !row.classList.contains('sr-matchup-split');
}

function rowGamesPlayed(table, row) {
    if (!isMatchupDataRow(row)) return 0;
    if (row.dataset.games !== undefined && row.dataset.games !== '') {
        const fromAttr = parseFloat(row.dataset.games);
        if (!isNaN(fromAttr)) return fromAttr;
    }
    const gamesIdx = findSortColumnIndex(table, 'games');
    if (gamesIdx >= 0) {
        const games = cellNumericValue(row, gamesIdx);
        if (!isNaN(games)) return games;
    }
    const wins = cellNumericValue(row, findSortColumnIndex(table, 'wins'));
    const losses = cellNumericValue(row, findSortColumnIndex(table, 'losses'));
    if (!isNaN(wins) && !isNaN(losses)) return wins + losses;
    return 0;
}

function rowMeetsMin(table, row, winPctMinGames) {
    if (!isMatchupDataRow(row)) return false;
    if (row.dataset.meetsMin === '1') return true;
    if (row.dataset.meetsMin === '0') return false;
    return rowGamesPlayed(table, row) >= winPctMinGames;
}

function winPctMinGamesForTable(table, rows) {
    const fromAttr = parseInt(table.dataset.winpctMinGames || '', 10);
    if (!isNaN(fromAttr) && fromAttr > 0) return fromAttr;

    const playerGames = parseInt(table.dataset.playerGames || '', 10);
    if (!isNaN(playerGames) && playerGames > 0) return playerMatchupMinGames(playerGames);

    let poolGames = 0;
    rows.forEach((row) => {
        if (isMatchupDataRow(row)) poolGames += rowGamesPlayed(table, row);
    });
    return playerMatchupMinGames(poolGames);
}

function syncMatchupSplitRow(table, dataRows, sortKey, winPctMinGames, collapsed) {
    const tbody = table.querySelector('tbody');
    if (!tbody) return null;
    let split = tbody.querySelector('.sr-matchup-split');
    const hasBothGroups = dataRows.some((row) => rowMeetsMin(table, row, winPctMinGames))
        && dataRows.some((row) => !rowMeetsMin(table, row, winPctMinGames));

    if (sortKey === 'winpct' && hasBothGroups) {
        if (!split) {
            split = document.createElement('tr');
            split.className = 'sr-matchup-split';
            const td = document.createElement('td');
            td.colSpan = table.querySelectorAll('thead th').length || 6;
            td.textContent = 'Fewer than ' + winPctMinGames + ' games';
            split.appendChild(td);
        }
        // Place divider after the last qualified row.
        let lastQual = null;
        dataRows.forEach((row) => {
            tbody.appendChild(row);
            if (rowMeetsMin(table, row, winPctMinGames)) lastQual = row;
        });
        if (lastQual && lastQual.nextSibling !== split) {
            tbody.insertBefore(split, lastQual.nextSibling);
        } else if (!lastQual) {
            tbody.insertBefore(split, tbody.firstChild);
        }
        if (collapsed) split.classList.add('sr-hidden');
        else split.classList.remove('sr-hidden');
        return split;
    }

    if (split) split.classList.add('sr-hidden');
    dataRows.forEach((row) => tbody.appendChild(row));
    return split;
}

function applyCollapsedRows(table, rows, sortKey, winPctMinGames, collapseLimit) {
    const dataRows = rows.filter(isMatchupDataRow);
    let shown = 0;
    if (sortKey === 'winpct' && winPctMinGames > 0) {
        dataRows.forEach((row) => {
            const qualifies = rowMeetsMin(table, row, winPctMinGames);
            if (!qualifies) {
                row.classList.add('sr-hidden');
                return;
            }
            shown += 1;
            if (shown > collapseLimit) row.classList.add('sr-hidden');
            else row.classList.remove('sr-hidden');
        });
        // Never leave the collapsed preview empty when there are rows.
        if (shown === 0 && dataRows.length) {
            dataRows.forEach((row, i) => {
                if (i >= collapseLimit) row.classList.add('sr-hidden');
                else row.classList.remove('sr-hidden');
            });
        }
        syncMatchupSplitRow(table, dataRows, sortKey, winPctMinGames, true);
        return;
    }
    dataRows.forEach((row) => {
        if (shown >= collapseLimit) row.classList.add('sr-hidden');
        else row.classList.remove('sr-hidden');
        shown += 1;
    });
    syncMatchupSplitRow(table, dataRows, sortKey, winPctMinGames, true);
}

function sortTable(table, columnIndex, direction, isNumeric) {
    const tbody = table.querySelector('tbody');
    if (!tbody) return;

    const allRows = Array.from(tbody.querySelectorAll('tr'));
    const dataRows = allRows.filter(isMatchupDataRow);
    const wasCollapsed = dataRows.some((row) => row.classList.contains('sr-hidden'));
    const collapseLimit = parseInt(table.dataset.collapseLimit || '5', 10);
    const sortHeader = table.querySelectorAll('th')[columnIndex];
    const sortKey = sortHeader ? sortHeader.dataset.sort : '';
    const winPctMinGames = winPctMinGamesForTable(table, dataRows);

    dataRows.sort((a, b) => {
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

            // Qualified sample first, then win%, then games as tiebreaker.
            if (sortKey === 'winpct') {
                const aGames = rowGamesPlayed(table, a);
                const bGames = rowGamesPlayed(table, b);
                const aQual = rowMeetsMin(table, a, winPctMinGames) ? 1 : 0;
                const bQual = rowMeetsMin(table, b, winPctMinGames) ? 1 : 0;
                if (aQual !== bQual) return bQual - aQual;

                if (aVal !== bVal) {
                    return direction === 'asc' ? aVal - bVal : bVal - aVal;
                }
                return bGames - aGames;
            }

            return direction === 'asc' ? aVal - bVal : bVal - aVal;
        }

        aVal = String(aVal).toLowerCase();
        bVal = String(bVal).toLowerCase();
        if (direction === 'asc') {
            return aVal.localeCompare(bVal);
        }
        return bVal.localeCompare(aVal);
    });

    syncMatchupSplitRow(table, dataRows, sortKey, winPctMinGames, wasCollapsed);

    let rank = 0;
    dataRows.forEach((row) => {
        rank += 1;
        const rankCell = row.querySelector('.sr-rank');
        if (rankCell) {
            rankCell.textContent = rank;
            if (table.classList.contains('sr-table')) {
                rankCell.className = 'sr-rank';
                if (rank === 1) rankCell.classList.add('sr-rank-1');
                else if (rank === 2) rankCell.classList.add('sr-rank-2');
                else if (rank === 3) rankCell.classList.add('sr-rank-3');
            }
        }
    });

    if (wasCollapsed) {
        applyCollapsedRows(table, dataRows, sortKey, winPctMinGames, collapseLimit);
    } else {
        syncMatchupSplitRow(table, dataRows, sortKey, winPctMinGames, false);
    }
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

// ============================================
// PLAYER PAGE STICKY NAME/FACE + SECTION HEADS
// ============================================
// Desktop: CSS position:sticky is reliable.
// Mobile/iOS: sticky slides away while scrolling; pin with position:fixed
// instead, using a scroll listener (not IO — URL-bar resize makes IO flicker).
function initPlayerPageSticky() {
    const header = document.querySelector('.sr-player-header');
    if (!header) return;

    const sections = document.querySelectorAll('.sr-player-section');
    const needsFixedPin = window.matchMedia('(hover: none) and (pointer: coarse)').matches
        || window.matchMedia('(max-width: 768px)').matches;

    function measureSectionOffsets() {
        sections.forEach((section) => {
            const title = section.querySelector('.sr-section-title');
            if (!title) return;
            section.style.setProperty(
                '--sr-section-title-h',
                Math.ceil(title.getBoundingClientRect().height) + 'px'
            );
        });
    }

    function publishStickyHeight(h) {
        document.documentElement.style.setProperty('--sr-player-sticky-h', h + 'px');
    }

    function measureHeaderHeight() {
        return Math.ceil(header.getBoundingClientRect().height);
    }

    // Desktop keeps pure sticky; still publish heights for section heads.
    if (!needsFixedPin) {
        publishStickyHeight(measureHeaderHeight());
        measureSectionOffsets();
        window.addEventListener('resize', function() {
            publishStickyHeight(measureHeaderHeight());
            measureSectionOffsets();
        });
        return;
    }

    const homeParent = header.parentNode;
    const sentinel = document.createElement('div');
    sentinel.className = 'sr-player-sticky-sentinel';
    sentinel.setAttribute('aria-hidden', 'true');
    homeParent.insertBefore(sentinel, header);

    const spacer = document.createElement('div');
    spacer.className = 'sr-player-sticky-spacer';
    spacer.setAttribute('aria-hidden', 'true');
    homeParent.insertBefore(spacer, header.nextSibling);

    // Spacer must match the in-flow header height. Never resize it while pinned —
    // remasuring on scroll (Safari URL bar) was yanking the page back to the top.
    let flowHeight = measureHeaderHeight();
    publishStickyHeight(flowHeight);

    function setPinned(pinned) {
        const isPinned = header.classList.contains('is-fixed');
        if (pinned === isPinned) return;

        // Preserve scroll across DOM reparent — iOS can otherwise jump to top.
        const scrollY = window.scrollY || window.pageYOffset || 0;

        if (pinned) {
            flowHeight = measureHeaderHeight();
            header.classList.add('is-fixed');
            // Reparent to <body> so iOS can't treat fixed as scrolling with a container.
            document.body.appendChild(header);
            spacer.style.height = flowHeight + 'px';
            publishStickyHeight(measureHeaderHeight());
        } else {
            header.classList.remove('is-fixed');
            homeParent.insertBefore(header, spacer);
            spacer.style.height = '0px';
            flowHeight = measureHeaderHeight();
            publishStickyHeight(flowHeight);
        }
        measureSectionOffsets();

        if ((window.scrollY || window.pageYOffset || 0) !== scrollY) {
            window.scrollTo(0, scrollY);
        }
    }

    function updatePinFromScroll() {
        const top = sentinel.getBoundingClientRect().top;
        const isPinned = header.classList.contains('is-fixed');
        if (isPinned) {
            // Wide hysteresis so slow scrolls / URL-bar resize don't unpin/repin.
            if (top > 24) setPinned(false);
        } else if (top < 0) {
            setPinned(true);
        }
    }

    let ticking = false;
    function onScroll() {
        if (ticking) return;
        ticking = true;
        window.requestAnimationFrame(function() {
            ticking = false;
            updatePinFromScroll();
        });
    }

    // Capture scroll on documentElement too — iOS sometimes scrolls the root, not window.
    window.addEventListener('scroll', onScroll, { passive: true });
    document.addEventListener('scroll', onScroll, { passive: true, capture: true });
    window.addEventListener('resize', function() {
        if (header.classList.contains('is-fixed')) {
            // Keep spacer stable; only refresh sticky offsets for section heads.
            publishStickyHeight(measureHeaderHeight());
        } else {
            flowHeight = measureHeaderHeight();
            publishStickyHeight(flowHeight);
        }
        measureSectionOffsets();
        updatePinFromScroll();
    });

    measureSectionOffsets();
    updatePinFromScroll();
}
window.initPlayerPageSticky = initPlayerPageSticky;

function toggleRows(tbodyId, btn, limit) {
    const tbody = document.getElementById(tbodyId);
    if (!tbody) return;

    const table = tbody.closest('table');
    const maxRows = limit || parseInt((table && table.dataset.collapseLimit) || '5', 10);
    const rows = Array.from(tbody.querySelectorAll('tr'));
    const hidden = tbody.querySelectorAll('.sr-hidden');
    if (!btn.dataset.expandLabel) btn.dataset.expandLabel = btn.textContent;

    if (hidden.length > 0) {
        hidden.forEach((row) => row.classList.remove('sr-hidden'));
        btn.textContent = 'Show less';
        return;
    }

    const st = table ? tableSortState.get(table) : null;
    const sortHeader = st && st.column >= 0 ? table.querySelectorAll('th')[st.column] : null;
    const sortKey = sortHeader ? sortHeader.dataset.sort : (table && table.dataset.defaultSort) || '';
    const winPctMinGames = sortKey === 'winpct' ? winPctMinGamesForTable(table, rows) : 0;
    applyCollapsedRows(table, rows, sortKey, winPctMinGames, maxRows);
    btn.textContent = btn.dataset.expandLabel;
}
window.toggleRows = toggleRows;

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