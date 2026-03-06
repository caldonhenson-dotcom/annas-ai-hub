/* ============================================================
   Response Cards — renders visual cards in the AI response canvas
   ============================================================ */
(function () {
    'use strict';

    var chartInstances = {};
    var CANVAS_ID = 'response-canvas';
    var palette = ['#3CB4AD','#334FB4','#a78bfa','#34d399','#f472b6','#f59e0b','#60a5fa','#ef4444'];

    function isDark() { return document.documentElement.getAttribute('data-theme') === 'dark'; }
    function tickCol() { return isDark() ? '#9ca3af' : '#94a3b8'; }
    function tipBg() { return isDark() ? '#1a1d27' : '#242833'; }

    /** Clear all cards from the response canvas. */
    function clearCanvas() {
        var el = document.getElementById(CANVAS_ID);
        if (!el) return;
        Object.keys(chartInstances).forEach(function (k) {
            if (chartInstances[k]) chartInstances[k].destroy();
            delete chartInstances[k];
        });
        el.innerHTML = '';
    }

    /** Create a base card element with optional header. */
    function createCard(title, icon, subtitle, extraClass) {
        var card = document.createElement('div');
        card.className = 'rc-card' + (extraClass ? ' ' + extraClass : '');
        if (title) {
            card.innerHTML = '<div class="rc-card-header">'
                + (icon ? '<div class="rc-card-icon">' + icon + '</div>' : '')
                + '<div><div class="rc-card-title">' + title + '</div>'
                + (subtitle ? '<div class="rc-card-subtitle">' + subtitle + '</div>' : '')
                + '</div></div>';
        }
        return card;
    }

    /** Append a card to the canvas. */
    function appendToCanvas(el) {
        var canvas = document.getElementById(CANVAS_ID);
        if (canvas) {
            var welcome = canvas.querySelector('.anna-canvas-welcome');
            if (welcome) welcome.remove();
            canvas.appendChild(el);
        }
    }

    // ------------------------------------------------------------------
    // Text Card
    // ------------------------------------------------------------------
    function renderTextCard(text, title) {
        var card = createCard(title || null, null, null, 'rc-text-card');
        var body = document.createElement('div');
        body.className = 'rc-card-body';
        body.innerHTML = typeof md === 'function' ? md(text) : text;
        card.appendChild(body);
        appendToCanvas(card);
        return card;
    }

    // ------------------------------------------------------------------
    // KPI Row
    // ------------------------------------------------------------------
    function renderKpiRow(kpis) {
        var row = document.createElement('div');
        row.className = 'rc-kpi-row';
        kpis.forEach(function (k) {
            var cls = 'neutral';
            if (k.change && k.change.indexOf('+') === 0) cls = 'up';
            else if (k.change && k.change.indexOf('-') === 0) cls = 'down';
            var div = document.createElement('div');
            div.className = 'rc-kpi-card';
            if (k.color) div.style.borderLeftColor = k.color;
            div.innerHTML = '<div class="rc-kpi-label">' + k.label + '</div>'
                + '<div class="rc-kpi-value">' + k.value + '</div>'
                + (k.change ? '<div class="rc-kpi-change ' + cls + '">' + k.change + '</div>' : '');
            row.appendChild(div);
        });
        appendToCanvas(row);
        return row;
    }

    // ------------------------------------------------------------------
    // Chart Card
    // ------------------------------------------------------------------
    function renderChartCard(spec) {
        var card = createCard(spec.title || 'Chart', spec.icon || '&#128202;', spec.subtitle || null);
        var container = document.createElement('div');
        container.className = 'rc-chart-container';
        var canvasEl = document.createElement('canvas');
        container.appendChild(canvasEl);
        card.appendChild(container);
        appendToCanvas(card);

        var cId = 'rc-chart-' + Date.now() + '-' + Math.random().toString(36).substr(2, 4);
        if (chartInstances[cId]) chartInstances[cId].destroy();

        var chartType = spec.chartType || spec.type || 'bar';
        var datasets = (spec.datasets || []).map(function (ds, i) {
            var bg = ds.color || palette[i % palette.length];
            // Doughnut needs an array of colors per data point
            if (chartType === 'doughnut') {
                bg = (ds.data || []).map(function (_, j) { return palette[j % palette.length] + 'CC'; });
            } else {
                bg = bg + 'CC';
            }
            return {
                label: ds.label || '',
                data: ds.data || [],
                backgroundColor: bg,
                borderColor: chartType === 'doughnut' ? '#fff' : (ds.color || palette[i % palette.length]),
                borderWidth: chartType === 'doughnut' ? 2 : (ds.borderWidth || 1),
                borderRadius: chartType === 'bar' ? 4 : 0,
                barPercentage: 0.7,
                fill: chartType === 'line',
                tension: 0.3,
                pointRadius: chartType === 'line' ? 2 : 0,
                pointHoverRadius: 5
            };
        });

        chartInstances[cId] = new Chart(canvasEl, {
            type: spec.chartType || spec.type || 'bar',
            data: { labels: spec.labels || [], datasets: datasets },
            options: buildChartOptions(spec)
        });
        return card;
    }

    function buildChartOptions(spec) {
        var isCurrency = spec.currency === true;
        var ct = spec.chartType || spec.type || 'bar';
        var showLegend = ct === 'doughnut' || (spec.datasets || []).length > 1;
        return {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: showLegend, position: ct === 'doughnut' ? 'right' : 'top',
                    labels: { font: { size: 11 }, color: tickCol(), boxWidth: 12, padding: 10 } },
                tooltip: {
                    backgroundColor: tipBg(), titleColor: '#fff', bodyColor: '#fff',
                    cornerRadius: 8, padding: 10,
                    callbacks: {
                        label: function (ctx) {
                            var v = ctx.raw;
                            var prefix = isCurrency ? '\u00a3' : '';
                            return (ctx.dataset.label ? ctx.dataset.label + ': ' : '')
                                + prefix + v.toLocaleString('en-GB');
                        }
                    }
                }
            },
            scales: {
                y: { display: spec.type !== 'doughnut', beginAtZero: true,
                    grid: { color: isDark() ? '#2a2d3a' : '#f1f1f4' },
                    ticks: { font: { size: 11 }, color: tickCol(),
                        callback: function (v) {
                            return isCurrency ? '\u00a3' + fmtNum(v) : fmtNum(v);
                        } } },
                x: { display: spec.type !== 'doughnut',
                    grid: { display: false }, border: { display: false },
                    ticks: { font: { size: 11, weight: '600' }, color: tickCol() } }
            }
        };
    }

    // ------------------------------------------------------------------
    // Table Card
    // ------------------------------------------------------------------
    function renderTableCard(spec) {
        var card = createCard(spec.title || 'Data', spec.icon || '&#128203;', spec.subtitle || null);
        var body = document.createElement('div');
        body.className = 'rc-card-body';
        body.style.padding = '0';
        var table = document.createElement('table');
        table.className = 'rc-table';

        var thead = '<thead><tr>' + (spec.columns || []).map(function (c) {
            return '<th>' + c + '</th>';
        }).join('') + '</tr></thead>';

        var tbody = '<tbody>' + (spec.rows || []).map(function (row) {
            return '<tr>' + row.map(function (cell) {
                return '<td>' + cell + '</td>';
            }).join('') + '</tr>';
        }).join('') + '</tbody>';

        table.innerHTML = thead + tbody;
        body.appendChild(table);
        card.appendChild(body);
        appendToCanvas(card);
        return card;
    }

    // ------------------------------------------------------------------
    // Board Card (Monday-style)
    // ------------------------------------------------------------------
    function renderBoardCard(spec) {
        var card = createCard(spec.title || 'Board', spec.icon || '&#128188;', spec.subtitle || null);
        var board = document.createElement('div');
        board.className = 'rc-board';

        var cols = spec.columns || ['Name', 'Status', 'Value', 'Owner', 'Progress'];
        board.innerHTML = '<div class="rc-board-header">' + cols.map(function (c) {
            return '<div>' + c + '</div>';
        }).join('') + '</div>';

        (spec.rows || []).forEach(function (r) {
            var row = document.createElement('div');
            row.className = 'rc-board-row';
            row.innerHTML = '<div class="rc-board-name">' + (r.name || '') + '</div>'
                + '<div>' + statusPill(r.status || 'default') + '</div>'
                + '<div class="rc-board-value">' + (r.value || '') + '</div>'
                + '<div>' + avatarEl(r.owner || '') + '</div>'
                + '<div>' + progressBar(r.progress || 0) + '</div>';
            board.appendChild(row);
        });

        card.appendChild(board);
        appendToCanvas(card);
        return card;
    }

    function statusPill(status) {
        var cls = 'default';
        var s = (status || '').toLowerCase();
        if (s.indexOf('working') >= 0 || s.indexOf('progress') >= 0) cls = 'working';
        else if (s.indexOf('done') >= 0 || s.indexOf('won') >= 0 || s.indexOf('complete') >= 0) cls = 'done';
        else if (s.indexOf('stuck') >= 0 || s.indexOf('lost') >= 0 || s.indexOf('risk') >= 0) cls = 'stuck';
        else if (s.indexOf('review') >= 0 || s.indexOf('cdd') >= 0) cls = 'review';
        else if (s.indexOf('new') >= 0 || s.indexOf('loi') >= 0) cls = 'new';
        return '<span class="rc-status-pill ' + cls + '">' + status + '</span>';
    }

    function avatarEl(name) {
        if (!name) return '';
        var initials = name.split(' ').map(function (w) { return w.charAt(0); }).join('').toUpperCase().substr(0, 2);
        return '<span class="rc-avatar">' + initials + '</span>';
    }

    function progressBar(pct) {
        pct = Math.max(0, Math.min(100, pct));
        return '<div class="rc-progress">'
            + '<div class="rc-progress-bar"><div class="rc-progress-fill" style="width:' + pct + '%"></div></div>'
            + '<div class="rc-progress-label">' + pct + '%</div></div>';
    }

    // ------------------------------------------------------------------
    // Mixed renderer — array of card specs
    // ------------------------------------------------------------------
    function renderMixed(cards) {
        clearCanvas();
        (cards || []).forEach(function (c) {
            switch (c.type) {
                case 'kpi': renderKpiRow(c.kpis || []); break;
                case 'chart': renderChartCard(c); break;
                case 'table': renderTableCard(c); break;
                case 'board': renderBoardCard(c); break;
                case 'text': renderTextCard(c.text || '', c.title || null); break;
            }
        });
    }

    // Expose
    window.ResponseCards = {
        clear: clearCanvas,
        text: renderTextCard,
        kpi: renderKpiRow,
        chart: renderChartCard,
        table: renderTableCard,
        board: renderBoardCard,
        mixed: renderMixed
    };

})();
