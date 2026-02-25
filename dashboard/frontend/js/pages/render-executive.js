/* ============================================================
   Render — Executive Summary (data-driven)
   ============================================================ */
(function () {
    'use strict';

    var D = window.STATIC;
    var esc = window.escHtml || function (s) { return s; };

    function renderKPIStrip(kpis) {
        var html = '<div class="exec-kpi-strip">';
        kpis.forEach(function (k) {
            html += '<div class="exec-kpi">'
                + '<div class="exec-kpi-val" style="color:' + k.color + '">' + k.value + '</div>'
                + '<div class="exec-kpi-label">' + esc(k.label) + '</div>'
                + '</div>';
        });
        return html + '</div>';
    }

    function renderPillars(pillars) {
        var html = '<div class="exec-pillars">';
        pillars.forEach(function (p) {
            html += '<div class="exec-pillar clickable" onclick="showPage(\'' + p.page + '\')">'
                + '<div class="exec-pillar-header">'
                + '<span class="exec-pillar-icon" style="background:' + p.color + '15;color:' + p.color + '">' + p.icon + '</span>'
                + '<span class="exec-pillar-title">' + esc(p.title) + '</span>'
                + '<span class="exec-pillar-arrow" style="color:' + p.color + '">&#8594;</span>'
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
        var html = '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:8px">';
        charts.forEach(function (c) {
            html += '<div class="glass-card" style="padding:10px 12px">'
                + '<div class="card-title" style="font-size:10px;margin-bottom:4px">' + esc(c.label) + '</div>'
                + '<div id="' + c.id + '"></div>'
                + '</div>';
        });
        return html + '</div>';
    }

    function renderTargetBar(t) {
        return '<div class="glass-card mt-2" style="padding:10px 14px">'
            + '<div class="text-muted-xs" style="text-transform:uppercase;letter-spacing:0.04em;margin-bottom:4px">'
            + 'Revenue Target Progress</div>'
            + '<div class="flex-between mb-1" style="font-size:13px">'
            + '<span class="text-label-sm">' + esc(t.label) + '</span>'
            + '<span class="text-primary">' + t.current.toLocaleString('en-GB') + ' / ' + t.target.toLocaleString('en-GB') + '</span>'
            + '</div>'
            + '<div style="height:10px;background:#e2e5ea;border-radius:5px;overflow:hidden">'
            + '<div style="height:100%;width:' + Math.min(100, t.pct).toFixed(1) + '%;'
            + 'background:linear-gradient(90deg,#34d399,#34d399cc);border-radius:5px"></div>'
            + '</div></div>';
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
