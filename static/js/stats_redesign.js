// Steam Charts-inspired Stats Page JavaScript

document.addEventListener('DOMContentLoaded', function() {
    initSearch();
    initSorting();
    initChart();
    initRangePills();
});

// ============================================
// SEARCH FILTERING
// ============================================
function initSearch() {
    const searchInput = document.getElementById('sr-search');
    if (!searchInput) return;
    
    const filterActive = document.getElementById('sr-filter-active');
    const filterChip = document.getElementById('sr-filter-chip');
    const noResults = document.getElementById('sr-no-results');
    
    // Get all sr-table elements on the page
    const tables = document.querySelectorAll('.sr-table');
    
    searchInput.addEventListener('input', function() {
        const query = this.value.toLowerCase().trim();
        filterAllTables(query, tables, filterActive, filterChip, noResults);
    });
    
    // Clear filter on chip close click
    const chipClose = document.getElementById('sr-filter-chip-close');
    if (chipClose) {
        chipClose.addEventListener('click', function() {
            searchInput.value = '';
            filterAllTables('', tables, filterActive, filterChip, noResults);
        });
    }
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
            const matches = query === '' || playerName.includes(query);
            
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
let currentSort = { column: 2, direction: 'desc' }; // Default: Rating desc

function initSorting() {
    const table = document.getElementById('sr-table');
    if (!table) return;
    
    const headers = table.querySelectorAll('th[data-sort]');
    
    headers.forEach((header, index) => {
        header.addEventListener('click', function() {
            const sortKey = this.dataset.sort;
            const isNumeric = this.classList.contains('sr-numeric');
            
            // Toggle direction if same column
            if (currentSort.column === index) {
                currentSort.direction = currentSort.direction === 'asc' ? 'desc' : 'asc';
            } else {
                currentSort.column = index;
                currentSort.direction = isNumeric ? 'desc' : 'asc'; // Default desc for numbers
            }
            
            sortTable(table, index, currentSort.direction, isNumeric);
            updateSortIndicators(headers, index, currentSort.direction);
        });
    });
    
    // Apply default sort
    const defaultHeader = headers[currentSort.column];
    if (defaultHeader) {
        const isNumeric = defaultHeader.classList.contains('sr-numeric');
        sortTable(table, currentSort.column, currentSort.direction, isNumeric);
        updateSortIndicators(headers, currentSort.column, currentSort.direction);
    }
}

function sortTable(table, columnIndex, direction, isNumeric) {
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    
    rows.sort((a, b) => {
        const aCell = a.cells[columnIndex];
        const bCell = b.cells[columnIndex];
        
        let aVal = aCell.dataset.value !== undefined ? aCell.dataset.value : aCell.textContent.trim();
        let bVal = bCell.dataset.value !== undefined ? bCell.dataset.value : bCell.textContent.trim();
        
        if (isNumeric) {
            aVal = parseFloat(aVal) || 0;
            bVal = parseFloat(bVal) || 0;
            return direction === 'asc' ? aVal - bVal : bVal - aVal;
        } else {
            aVal = aVal.toLowerCase();
            bVal = bVal.toLowerCase();
            if (direction === 'asc') {
                return aVal.localeCompare(bVal);
            } else {
                return bVal.localeCompare(aVal);
            }
        }
    });
    
    // Re-append sorted rows and update rank numbers
    rows.forEach((row, index) => {
        tbody.appendChild(row);
        const rankCell = row.querySelector('.sr-rank');
        if (rankCell) {
            rankCell.textContent = index + 1;
            rankCell.className = 'sr-rank';
            if (index === 0) rankCell.classList.add('sr-rank-1');
            else if (index === 1) rankCell.classList.add('sr-rank-2');
            else if (index === 2) rankCell.classList.add('sr-rank-3');
        }
    });
}

function updateSortIndicators(headers, activeIndex, direction) {
    headers.forEach((header, index) => {
        const arrow = header.querySelector('.sr-sort-arrow');
        if (!arrow) return;
        
        if (index === activeIndex) {
            header.classList.add('sr-sorted');
            arrow.textContent = direction === 'asc' ? '▲' : '▼';
        } else {
            header.classList.remove('sr-sorted');
            arrow.textContent = '▼';
        }
    });
}

// ============================================
// CHART
// ============================================
let heroChart = null;

function initChart() {
    const canvas = document.getElementById('heroChart');
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    const year = canvas.dataset.year || new Date().getFullYear();
    
    fetchChartData(year, 'all').then(data => {
        renderChart(ctx, data);
    });
}

function fetchChartData(year, range) {
    return fetch(`/api/stats/hero?year=${year}&range=${range}`)
        .then(response => response.json())
        .catch(error => {
            console.error('Chart data fetch error:', error);
            return { labels: [], series: [] };
        });
}

function renderChart(ctx, data) {
    if (heroChart) {
        heroChart.destroy();
    }
    
    const colors = [
        '#6ee7ff', '#4ade80', '#fbbf24', '#f87171', '#a78bfa',
        '#fb923c', '#38bdf8', '#34d399', '#facc15', '#f472b6'
    ];
    
    // If no time series, render as bar chart
    const isBarChart = !data.labels || data.labels.length <= 1;
    
    if (isBarChart && data.series && data.series.length > 0) {
        // Bar chart for top players by rating
        heroChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: data.series.map(s => s.name),
                datasets: [{
                    label: 'Rating',
                    data: data.series.map(s => s.values[0] || s.value || 0),
                    backgroundColor: colors.slice(0, data.series.length).map(c => c + '80'),
                    borderColor: colors.slice(0, data.series.length),
                    borderWidth: 2,
                    borderRadius: 4
                }]
            },
            options: getChartOptions('bar')
        });
    } else if (data.series && data.series.length > 0) {
        // Line chart for time series
        heroChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.labels,
                datasets: data.series.map((series, i) => ({
                    label: series.name,
                    data: series.values,
                    borderColor: colors[i % colors.length],
                    backgroundColor: colors[i % colors.length] + '20',
                    borderWidth: 2,
                    tension: 0.3,
                    fill: false,
                    pointRadius: 3,
                    pointHoverRadius: 5
                }))
            },
            options: getChartOptions('line')
        });
    }
}

function getChartOptions(type) {
    return {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
            intersect: false,
            mode: 'index'
        },
        plugins: {
            legend: {
                display: type === 'line',
                position: 'top',
                labels: {
                    color: '#9aa4b2',
                    font: { size: 11 },
                    boxWidth: 12,
                    padding: 15
                }
            },
            tooltip: {
                backgroundColor: 'rgba(15, 22, 32, 0.95)',
                titleColor: '#e6edf3',
                bodyColor: '#e6edf3',
                borderColor: 'rgba(255, 255, 255, 0.1)',
                borderWidth: 1,
                padding: 12,
                cornerRadius: 8,
                displayColors: true
            }
        },
        scales: {
            x: {
                grid: {
                    color: 'rgba(255, 255, 255, 0.05)',
                    drawBorder: false
                },
                ticks: {
                    color: '#9aa4b2',
                    font: { size: 11 }
                }
            },
            y: {
                grid: {
                    color: 'rgba(255, 255, 255, 0.05)',
                    drawBorder: false
                },
                ticks: {
                    color: '#9aa4b2',
                    font: { size: 11 }
                },
                beginAtZero: type === 'bar'
            }
        }
    };
}

// ============================================
// RANGE PILLS
// ============================================
function initRangePills() {
    const pills = document.querySelectorAll('.sr-range-pill');
    const canvas = document.getElementById('heroChart');
    
    if (!pills.length || !canvas) return;
    
    const year = canvas.dataset.year || new Date().getFullYear();
    
    pills.forEach(pill => {
        pill.addEventListener('click', function() {
            const range = this.dataset.range;
            
            // Update active state
            pills.forEach(p => p.classList.remove('active'));
            this.classList.add('active');
            
            // Fetch and render new data
            const ctx = canvas.getContext('2d');
            fetchChartData(year, range).then(data => {
                renderChart(ctx, data);
            });
        });
    });
}
