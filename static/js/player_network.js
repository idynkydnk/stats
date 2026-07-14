(function () {
    'use strict';

    var dataEl = document.getElementById('pn-data');
    var svgEl = document.getElementById('pn-chart');
    if (!dataEl || !svgEl || typeof d3 === 'undefined') {
        return;
    }

    var payload = JSON.parse(dataEl.textContent || '{}');
    var allNodes = (payload.nodes || []).map(function (node) {
        return {
            id: node.id,
            label: shortLabel(node.label || node.id),
            games: node.games || 0,
        };
    });
    var partnerEdges = payload.partner_edges || [];
    var gameEdges = payload.game_edges || [];
    var year = payload.year || '';
    var playerUrlTemplate = payload.player_url_template || '';

    var mode = 'partner';
    var minGames = 1;
    var selectedNodeId = null;
    var selectedEdgeKey = null;
    var simulation = null;

    var modePills = document.getElementById('pn-mode-pills');
    var minGamesInput = document.getElementById('pn-min-games');
    var minGamesValue = document.getElementById('pn-min-games-value');
    var clearBtn = document.getElementById('pn-clear-selection');
    var detailsEl = document.getElementById('pn-details');

    function shortLabel(name) {
        var parts = String(name || '').trim().split(/\s+/);
        if (parts.length <= 1) {
            return parts[0] || '';
        }
        return parts[0] + ' ' + parts[parts.length - 1].charAt(0) + '.';
    }

    function playerUrl(name) {
        return playerUrlTemplate.replace('__NAME__', encodeURIComponent(name));
    }

    function edgeKey(edge) {
        return [edge.source.id || edge.source, edge.target.id || edge.target].sort().join('||');
    }

    function activeEdgesRaw() {
        return mode === 'partner' ? partnerEdges : gameEdges;
    }

    function filteredEdges() {
        return activeEdgesRaw().filter(function (edge) {
            return (edge.games || 0) >= minGames;
        });
    }

    function connectedNodeIds(edges) {
        var ids = {};
        edges.forEach(function (edge) {
            ids[edge.source] = true;
            ids[edge.target] = true;
        });
        return ids;
    }

    function winRateColor(rate) {
        var clamped = Math.max(0, Math.min(1, rate || 0));
        if (clamped <= 0.5) {
            return d3.interpolateRgb('#ef4444', '#fbbf24')(clamped / 0.5);
        }
        return d3.interpolateRgb('#fbbf24', '#22c55e')((clamped - 0.5) / 0.5);
    }

    function edgeColor(edge) {
        if (mode === 'partner') {
            return winRateColor(edge.win_rate);
        }
        return '#64748b';
    }

    function edgeWidth(edge, scale) {
        return scale(edge.games || 1);
    }

    function setDetails(titleHtml, bodyHtml) {
        detailsEl.innerHTML =
            '<p class="pn-details-title">' + titleHtml + '</p>' +
            '<p class="pn-details-body">' + bodyHtml + '</p>';
    }

    function defaultDetails() {
        setDetails(
            'Tap a player or connection',
            'Select a circle to highlight that player\'s connections, or tap a line to see how often two players share games.'
        );
    }

    function showNodeDetails(node) {
        setDetails(
            escapeHtml(node.label) + ' <a href="' + escapeHtml(playerUrl(node.id)) + '">View stats</a>',
            node.games + ' game' + (node.games === 1 ? '' : 's') + ' in ' + escapeHtml(String(year)) + '.'
        );
    }

    function showEdgeDetails(edge) {
        var source = edge.source.id || edge.source;
        var target = edge.target.id || edge.target;
        var sourceLabel = shortLabel(source);
        var targetLabel = shortLabel(target);
        if (mode === 'partner') {
            var pct = Math.round((edge.win_rate || 0) * 100);
            setDetails(
                escapeHtml(sourceLabel) + ' &amp; ' + escapeHtml(targetLabel),
                edge.games + ' game' + (edge.games === 1 ? '' : 's') + ' together as teammates — ' +
                edge.wins + '-' + edge.losses + ' (' + pct + '% win rate).'
            );
            return;
        }
        setDetails(
            escapeHtml(sourceLabel) + ' &amp; ' + escapeHtml(targetLabel),
            edge.games + ' shared game' + (edge.games === 1 ? '' : 's') + ' in ' + escapeHtml(String(year)) + '.'
        );
    }

    function escapeHtml(value) {
        return String(value || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function updateClearButton() {
        if (!clearBtn) {
            return;
        }
        clearBtn.style.display = (selectedNodeId || selectedEdgeKey) ? '' : 'none';
    }

    function clearSelection() {
        selectedNodeId = null;
        selectedEdgeKey = null;
        updateClearButton();
        defaultDetails();
        render();
    }

    function render() {
        var edgesData = filteredEdges();
        var linkedIds = connectedNodeIds(edgesData);
        var visibleNodes = allNodes.filter(function (node) {
            return linkedIds[node.id];
        });

        if (!visibleNodes.length) {
            svgEl.innerHTML = '';
            setDetails(
                'No connections at this threshold',
                'Try lowering Min games or switch modes to see more pairs.'
            );
            return;
        }

        var width = svgEl.clientWidth || 900;
        var height = svgEl.clientHeight || 640;
        var maxGames = d3.max(visibleNodes, function (d) { return d.games; }) || 1;
        var maxEdgeGames = d3.max(edgesData, function (d) { return d.games; }) || 1;

        var radiusScale = d3.scaleSqrt()
            .domain([1, maxGames])
            .range([10, 34]);

        var edgeWidthScale = d3.scaleSqrt()
            .domain([1, maxEdgeGames])
            .range([1.2, 8]);

        var links = edgesData.map(function (edge) {
            return {
                source: edge.source,
                target: edge.target,
                games: edge.games,
                wins: edge.wins,
                losses: edge.losses,
                win_rate: edge.win_rate,
                key: edgeKey(edge),
            };
        });

        var nodes = visibleNodes.map(function (node) {
            return {
                id: node.id,
                label: node.label,
                games: node.games,
                radius: radiusScale(node.games),
            };
        });

        d3.select(svgEl).selectAll('*').remove();
        var svg = d3.select(svgEl)
            .attr('viewBox', [0, 0, width, height]);

        var root = svg.append('g').attr('class', 'pn-root');

        var zoom = d3.zoom()
            .scaleExtent([0.35, 3])
            .on('zoom', function (event) {
                root.attr('transform', event.transform);
            });
        svg.call(zoom).on('dblclick.zoom', null);

        svg.on('click', function (event) {
            if (event.target === svgEl) {
                clearSelection();
            }
        });

        simulation = d3.forceSimulation(nodes)
            .force('link', d3.forceLink(links)
                .id(function (d) { return d.id; })
                .distance(function (d) { return 130 - Math.min((d.games || 1) * 2.5, 70); })
                .strength(0.55))
            .force('charge', d3.forceManyBody().strength(function (d) { return -220 - d.games * 3; }))
            .force('center', d3.forceCenter(width / 2, height / 2))
            .force('collision', d3.forceCollide().radius(function (d) { return d.radius + 8; }));

        var link = root.append('g')
            .attr('class', 'pn-links')
            .selectAll('line')
            .data(links)
            .join('line')
            .attr('class', 'pn-link')
            .attr('stroke', function (d) { return edgeColor(d); })
            .attr('stroke-width', function (d) { return edgeWidth(d, edgeWidthScale); })
            .attr('stroke-opacity', function (d) {
                if (selectedEdgeKey && d.key !== selectedEdgeKey) {
                    return 0.12;
                }
                if (selectedNodeId) {
                    var sourceId = d.source.id || d.source;
                    var targetId = d.target.id || d.target;
                    if (sourceId !== selectedNodeId && targetId !== selectedNodeId) {
                        return 0.12;
                    }
                }
                return 0.85;
            })
            .on('click', function (event, d) {
                event.stopPropagation();
                selectedEdgeKey = d.key;
                selectedNodeId = null;
                updateClearButton();
                showEdgeDetails(d);
                updateHighlight();
            });

        var node = root.append('g')
            .attr('class', 'pn-nodes')
            .selectAll('g')
            .data(nodes)
            .join('g')
            .attr('cursor', 'pointer')
            .call(d3.drag()
                .on('start', dragStarted)
                .on('drag', dragged)
                .on('end', dragEnded))
            .on('click', function (event, d) {
                event.stopPropagation();
                selectedNodeId = d.id;
                selectedEdgeKey = null;
                updateClearButton();
                showNodeDetails(d);
                updateHighlight();
            });

        node.append('circle')
            .attr('r', function (d) { return d.radius; })
            .attr('fill', '#86efac')
            .attr('fill-opacity', function (d) {
                if (!selectedNodeId && !selectedEdgeKey) {
                    return 0.92;
                }
                if (selectedNodeId && d.id !== selectedNodeId && !isNodeConnected(d.id)) {
                    return 0.18;
                }
                return 0.92;
            })
            .attr('stroke', function (d) {
                if (selectedNodeId === d.id) {
                    return '#66d9ef';
                }
                return '#14532d';
            })
            .attr('stroke-width', function (d) {
                return selectedNodeId === d.id ? 3 : 1.5;
            });

        node.append('text')
            .attr('class', 'pn-node-label')
            .attr('dy', function (d) { return d.radius + 14; })
            .text(function (d) { return d.label; })
            .attr('opacity', function (d) {
                if (!selectedNodeId && !selectedEdgeKey) {
                    return 1;
                }
                if (selectedNodeId && d.id !== selectedNodeId && !isNodeConnected(d.id)) {
                    return 0.25;
                }
                return 1;
            });

        function isNodeConnected(nodeId) {
            if (!selectedNodeId) {
                return true;
            }
            if (nodeId === selectedNodeId) {
                return true;
            }
            return links.some(function (linkData) {
                var sourceId = linkData.source.id || linkData.source;
                var targetId = linkData.target.id || linkData.target;
                return (sourceId === selectedNodeId && targetId === nodeId) ||
                    (targetId === selectedNodeId && sourceId === nodeId);
            });
        }

        function updateHighlight() {
            link.attr('stroke-opacity', function (d) {
                if (selectedEdgeKey && d.key !== selectedEdgeKey) {
                    return 0.12;
                }
                if (selectedNodeId) {
                    var sourceId = d.source.id || d.source;
                    var targetId = d.target.id || d.target;
                    if (sourceId !== selectedNodeId && targetId !== selectedNodeId) {
                        return 0.12;
                    }
                }
                return 0.85;
            });
            node.select('circle')
                .attr('fill-opacity', function (d) {
                    if (!selectedNodeId && !selectedEdgeKey) {
                        return 0.92;
                    }
                    if (selectedNodeId && d.id !== selectedNodeId && !isNodeConnected(d.id)) {
                        return 0.18;
                    }
                    return 0.92;
                })
                .attr('stroke', function (d) {
                    return selectedNodeId === d.id ? '#66d9ef' : '#14532d';
                })
                .attr('stroke-width', function (d) {
                    return selectedNodeId === d.id ? 3 : 1.5;
                });
            node.select('text')
                .attr('opacity', function (d) {
                    if (!selectedNodeId && !selectedEdgeKey) {
                        return 1;
                    }
                    if (selectedNodeId && d.id !== selectedNodeId && !isNodeConnected(d.id)) {
                        return 0.25;
                    }
                    return 1;
                });
        }

        simulation.on('tick', function () {
            link
                .attr('x1', function (d) { return d.source.x; })
                .attr('y1', function (d) { return d.source.y; })
                .attr('x2', function (d) { return d.target.x; })
                .attr('y2', function (d) { return d.target.y; });
            node.attr('transform', function (d) {
                return 'translate(' + d.x + ',' + d.y + ')';
            });
        });

        function dragStarted(event, d) {
            if (!event.active) {
                simulation.alphaTarget(0.3).restart();
            }
            d.fx = d.x;
            d.fy = d.y;
        }

        function dragged(event, d) {
            d.fx = event.x;
            d.fy = event.y;
        }

        function dragEnded(event, d) {
            if (!event.active) {
                simulation.alphaTarget(0);
            }
            d.fx = null;
            d.fy = null;
        }
    }

    if (modePills) {
        modePills.addEventListener('click', function (event) {
            var btn = event.target.closest('[data-mode]');
            if (!btn) {
                return;
            }
            mode = btn.getAttribute('data-mode') || 'partner';
            modePills.querySelectorAll('.sr-range-pill').forEach(function (pill) {
                pill.classList.toggle('active', pill === btn);
            });
            clearSelection();
        });
    }

    if (minGamesInput) {
        minGamesInput.addEventListener('input', function () {
            minGames = parseInt(minGamesInput.value, 10) || 1;
            if (minGamesValue) {
                minGamesValue.textContent = String(minGames);
            }
            selectedEdgeKey = null;
            updateClearButton();
            if (!selectedNodeId) {
                defaultDetails();
            }
            render();
        });
    }

    if (clearBtn) {
        clearBtn.addEventListener('click', clearSelection);
    }

    var resizeTimer = null;
    window.addEventListener('resize', function () {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(render, 150);
    });

    render();
})();
