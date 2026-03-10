/* ============================================================
   Render — Executive Summary (data-driven)
   ============================================================ */
(function () {
    'use strict';

    var D = window.STATIC;
    var esc = window.escHtml || function (s) { return s; };

    /* Color hex → CSS class suffix mapping */
    var THEME = {
        '#3CB4AD': 'teal', '#3cb4ad': 'teal',
        '#334FB4': 'blue', '#334fb4': 'blue',
        '#34d399': 'green',
        '#a78bfa': 'purple', '#8B5CF6': 'purple', '#8b5cf6': 'purple',
        '#f59e0b': 'amber', '#F59E0B': 'amber',
        '#3b82f6': 'info', '#3B82F6': 'info',
        '#f472b6': 'pink', '#F472B6': 'pink'
    };

    function colorClass(prefix, color) {
        var t = THEME[color] || THEME[(color || '').toLowerCase()];
        return t ? prefix + ' ' + prefix + '--' + t : prefix;
    }

    function colorFallback(color) {
        var t = THEME[color] || THEME[(color || '').toLowerCase()];
        return t ? '' : ' style="color:' + color + '"';
    }

    function renderKPIStrip(kpis) {
        var html = '<div class="exec-kpi-strip">';
        kpis.forEach(function (k) {
            html += '<div class="exec-kpi">'
                + '<div class="' + colorClass('exec-kpi-val', k.color) + '"' + colorFallback(k.color) + '>' + k.value + '</div>'
                + '<div class="exec-kpi-label">' + esc(k.label) + '</div>'
                + '</div>';
        });
        return html + '</div>';
    }

    function renderPillars(pillars) {
        var html = '<div class="exec-pillars">';
        pillars.forEach(function (p) {
            html += '<div class="exec-pillar" onclick="showPage(\'' + p.page + '\')">'
                + '<div class="exec-pillar-header">'
                + '<span class="' + colorClass('exec-pillar-icon', p.color) + '">' + p.icon + '</span>'
                + '<span class="exec-pillar-title">' + esc(p.title) + '</span>'
                + '<span class="' + colorClass('exec-pillar-arrow', p.color) + '">&#8594;</span>'
                + '</div>'
                + '<ul class="exec-pillar-points">';
            p.points.forEach(function (pt) {
                html += '<li>' + pt + '</li>';
            });
            html += '</ul></div>';
        });
        return html + '</div>';
    }

    function renderChartGrid(charts) {
        var html = '<div class="exec-spark-grid">';
        charts.forEach(function (c) {
            html += '<div class="glass-card exec-spark-card">'
                + '<div class="card-title exec-spark-title">' + esc(c.label) + '</div>'
                + '<div id="' + c.id + '"></div>'
                + '</div>';
        });
        return html + '</div>';
    }

    function renderTargetBar(t) {
        return '<div class="glass-card exec-target-card">'
            + '<div class="exec-target-label">Revenue Target Progress</div>'
            + '<div>'
            + '<div class="exec-target-values">'
            + '<span class="exec-target-hint">' + esc(t.label) + '</span>'
            + '<span class="text-primary">' + t.current.toLocaleString('en-GB') + ' / ' + t.target.toLocaleString('en-GB') + '</span>'
            + '</div>'
            + '<div class="exec-target-track">'
            + '<div class="progress-fill exec-target-fill" style="width:' + Math.min(100, t.pct).toFixed(1) + '%"></div>'
            + '</div></div></div>';
    }

    // Time saved KPI — reads skill execution history from localStorage directly
    function getTimeSaved() {
        try {
            var h = JSON.parse(localStorage.getItem('ecomplete_skill_history') || '[]');
            var now = Date.now();
            var today = h.filter(function (e) { return e.success && (now - e.timestamp) < 86400000; });
            var saved = today.length * 15; // ~15 min saved per successful skill run
            var hrs = Math.floor(saved / 60);
            var mins = saved % 60;
            return hrs > 0 ? hrs + 'h ' + mins + 'm' : mins + 'm';
        } catch (e) { return '0m'; }
    }

    window.renderExecutive = function () {
        var container = document.getElementById('page-executive');
        if (!container || !D) return;

        var section = container.querySelector('#executive') || container;
        var bodyEl = section.querySelector('.exec-body');
        if (!bodyEl) {
            bodyEl = document.createElement('div');
            bodyEl.className = 'exec-body';
            var header = section.querySelector('.section-header');
            if (header) {
                while (header.nextSibling) header.nextSibling.remove();
                section.appendChild(bodyEl);
            } else {
                section.innerHTML = '';
                section.appendChild(bodyEl);
            }
        }

        var kpis = (D.EXEC_KPIS || []).concat([{
            label: 'AI Time Saved Today', value: getTimeSaved(), color: '#f59e0b'
        }]);

        bodyEl.innerHTML = renderKPIStrip(kpis)
            + renderPillars(D.EXEC_PILLARS)
            + renderChartGrid(D.EXEC_CHARTS)
            + renderTargetBar(D.EXEC_TARGET);
    };
})();
