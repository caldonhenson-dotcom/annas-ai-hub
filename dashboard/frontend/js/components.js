/* ============================================================
   UI Components — reusable render functions
   ============================================================ */
(function () {
    'use strict';

    var esc = window.escHtml || function (s) { return s; };

    // ------------------------------------------------------------------
    // statCard — KPI stat card with optional trend badge & nav target
    // ------------------------------------------------------------------
    function statCard(label, value, opts) {
        opts = opts || {};
        var accent = opts.accent || 'var(--accent)';
        var nav = opts.navPage ? ' data-nav-page="' + esc(opts.navPage) + '"' : '';
        var trend = '';
        if (opts.trend !== undefined && opts.trend !== null) {
            trend = yoyBadge(opts.trend);
        }
        return '<div class="stat-card"' + nav + ' style="--accent:' + accent + '">'
            + '<div style="text-transform:uppercase;letter-spacing:0.04em;font-size:11px;'
            + 'color:var(--text-muted);font-weight:600;margin-bottom:6px">'
            + esc(label) + '</div>'
            + '<div data-role="stat-value" style="font-size:var(--text-2xl);font-weight:800;'
            + 'color:var(--text);line-height:1.2"'
            + (opts.countUp ? ' data-count-up="' + value + '"' : '')
            + '>' + value + trend + '</div>'
            + (opts.subtitle ? '<div class="text-muted-sm" style="margin-top:4px">' + esc(opts.subtitle) + '</div>' : '')
            + '</div>';
    }

    // ------------------------------------------------------------------
    // glassCard — standard content card with title
    // ------------------------------------------------------------------
    function glassCard(title, bodyHtml, opts) {
        opts = opts || {};
        var id = opts.id ? ' id="' + esc(opts.id) + '"' : '';
        var subtitle = opts.subtitle
            ? '<span class="text-muted-sm" style="margin-left:8px;font-weight:400">' + esc(opts.subtitle) + '</span>'
            : '';
        return '<div class="glass-card"' + id + '>'
            + (title ? '<div class="card-title">' + esc(title) + subtitle + '</div>' : '')
            + bodyHtml
            + '</div>';
    }

    // ------------------------------------------------------------------
    // statusPill — colored pill badge
    // ------------------------------------------------------------------
    var PILL_COLORS = {
        green:  { bg: 'rgba(34,197,94,0.12)',  color: '#16a34a' },
        red:    { bg: 'rgba(239,68,68,0.12)',   color: '#dc2626' },
        amber:  { bg: 'rgba(245,158,11,0.12)',  color: '#f59e0b' },
        blue:   { bg: 'rgba(59,130,246,0.12)',   color: '#3b82f6' },
        purple: { bg: 'rgba(139,92,246,0.12)',   color: '#8b5cf6' },
        teal:   { bg: 'rgba(60,180,173,0.12)',   color: '#3CB4AD' },
        gray:   { bg: 'rgba(107,114,128,0.1)',   color: '#6b7280' }
    };

    function statusPill(text, variant) {
        var c = PILL_COLORS[variant] || PILL_COLORS.gray;
        return '<span class="status-pill" style="background:' + c.bg + ';color:' + c.color + '">'
            + esc(text) + '</span>';
    }

    // ------------------------------------------------------------------
    // progressMini — 6px horizontal progress bar with percentage
    // ------------------------------------------------------------------
    function progressMini(pct, color) {
        pct = Math.min(100, Math.max(0, pct || 0));
        color = color || 'var(--accent)';
        return '<div class="progress-mini">'
            + '<div class="bar"><div class="bar-fill" style="width:'
            + pct.toFixed(1) + '%;background:' + color + '"></div></div>'
            + '<span class="pct">' + Math.round(pct) + '%</span></div>';
    }

    // ------------------------------------------------------------------
    // yoyBadge — up/down/neutral trend badge
    // ------------------------------------------------------------------
    function yoyBadge(value) {
        if (value === null || value === undefined) return '';
        var num = typeof value === 'number' ? value : parseFloat(value);
        if (isNaN(num)) return '';
        var cls, arrow;
        if (num > 0) { cls = 'up'; arrow = '&#9650;'; }
        else if (num < 0) { cls = 'down'; arrow = '&#9660;'; }
        else { cls = 'neutral'; arrow = '&#9644;'; }
        return '<span class="yoy-badge ' + cls + '">'
            + arrow + ' ' + Math.abs(num).toFixed(1) + '%</span>';
    }

    // ------------------------------------------------------------------
    // boardRow — Monday-style grid row
    // ------------------------------------------------------------------
    function boardRow(cells, opts) {
        opts = opts || {};
        var cls = 'board-row' + (opts.clickable ? ' ic-row clickable' : '');
        var attrs = opts.dataId ? ' data-id="' + esc(opts.dataId) + '"' : '';
        var html = '<div class="' + cls + '"' + attrs + '>';
        cells.forEach(function (cell) {
            html += '<div' + (cell.cls ? ' class="' + cell.cls + '"' : '') + '>'
                + (cell.html || esc(cell.text || '')) + '</div>';
        });
        html += '</div>';
        return html;
    }

    // ------------------------------------------------------------------
    // boardGroup — collapsible group header + rows container
    // ------------------------------------------------------------------
    function boardGroup(title, color, count, rowsHtml) {
        var id = 'grp-' + title.replace(/[^a-zA-Z0-9]/g, '-').toLowerCase();
        return '<div class="board-group">'
            + '<div class="board-group-header clickable" onclick="this.querySelector(\'.group-arrow\').classList.toggle(\'expanded\');'
            + 'this.nextElementSibling.style.display=this.nextElementSibling.style.display===\'none\'?\'block\':\'none\'">'
            + '<div class="group-color" style="background:' + (color || 'var(--accent)') + '"></div>'
            + '<div class="group-title">' + esc(title) + '</div>'
            + '<span class="group-count">' + (count || 0) + ' items</span>'
            + '<span class="group-arrow expanded">&#9654;</span>'
            + '</div>'
            + '<div class="board-rows">' + (rowsHtml || '') + '</div>'
            + '</div>';
    }

    // ------------------------------------------------------------------
    // dataTable — renders a full data table (headers + rows)
    // ------------------------------------------------------------------
    function dataTable(headers, rows, opts) {
        opts = opts || {};
        var tableId = opts.id || ('tbl-' + Math.random().toString(36).substr(2, 6));
        var html = '<div class="table-wrapper">'
            + '<table class="data-table" id="' + tableId + '">'
            + '<thead><tr>';
        headers.forEach(function (h, i) {
            var sortAttr = opts.sortable !== false
                ? ' onclick="sortTable(\'' + tableId + '\',' + i + ')"'
                : '';
            html += '<th' + sortAttr + '>' + esc(typeof h === 'string' ? h : h.label || '')
                + (opts.sortable !== false ? ' <span class="sort-arrow">&#9650;</span>' : '')
                + '</th>';
        });
        html += '</tr></thead><tbody>';
        rows.forEach(function (row) {
            html += '<tr>';
            row.forEach(function (cell) {
                html += '<td>' + (typeof cell === 'object' && cell.html ? cell.html : esc(String(cell))) + '</td>';
            });
            html += '</tr>';
        });
        html += '</tbody></table></div>';
        return html;
    }

    // ------------------------------------------------------------------
    // Expose on window.UI
    // ------------------------------------------------------------------
    window.UI = {
        statCard: statCard,
        glassCard: glassCard,
        statusPill: statusPill,
        progressMini: progressMini,
        yoyBadge: yoyBadge,
        boardRow: boardRow,
        boardGroup: boardGroup,
        dataTable: dataTable
    };
})();
