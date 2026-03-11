/* ============================================================
   Render — Inbound Queue KPI + category + source cards
   ============================================================ */
(function () {
    'use strict';

    var D = window.STATIC;
    var esc = window.escHtml || function (s) { return s; };

    function renderKPIs(kpis) {
        var html = '<div class="kpi-grid">';
        kpis.forEach(function (k) {
            html += '<div class="stat-card" style="--accent:' + k.accent + '">'
                + '<div class="exec-pillar-icon" style="width:20px;height:20px;border-radius:5px;'
                + 'background:linear-gradient(135deg,' + k.accent + '22,' + k.accent + '11);'
                + 'border:1px solid ' + k.accent + '33;font-size:11px;margin-bottom:2px">' + k.icon + '</div>'
                + '<div class="pl-act-label">' + esc(k.label) + '</div>'
                + '<div class="pl-act-value">' + k.value + '</div>'
                + '<div class="text-muted-sm">' + esc(k.subtitle) + '</div>'
                + '</div>';
        });
        return html + '</div>';
    }

    function renderCategories(cats) {
        var html = '<div class="glass-card"><div class="card-title">Signal Categories</div>'
            + '<div class="pl-active-chips" style="margin-top:6px">';
        cats.forEach(function (c) {
            html += '<span class="pl-chip" style="color:' + c.color + ';background:' + c.color + '12;'
                + 'border:1px solid ' + c.color + '30">'
                + esc(c.label) + ': ' + c.count + '</span>';
        });
        return html + '</div></div>';
    }

    function renderSources(sources) {
        var html = '<div class="glass-card"><div class="card-title">By Source</div>'
            + '<div class="stat-mini-grid" style="grid-template-columns:repeat(' + sources.length + ',1fr);margin-top:6px">';
        sources.forEach(function (s) {
            html += '<div class="stat-mini-item">'
                + '<div style="font-size:16px">' + s.icon + '</div>'
                + '<div class="stat-mini-value" style="font-weight:700">' + s.count + '</div>'
                + '<div class="stat-mini-sub cell-pad-cap">' + esc(s.label) + '</div>'
                + '</div>';
        });
        return html + '</div></div>';
    }

    window.renderInbound = function () {
        var container = document.getElementById('page-inbound-queue');
        if (!container || !D) return;

        // Find existing content markers
        var section = container.querySelector('.dashboard-section') || container;
        var kpiGrid = section.querySelector('.kpi-grid');
        var cards = section.querySelectorAll('.glass-card');

        // Only re-render the dynamic sections if data is available
        if (kpiGrid && D.INBOUND_KPIS) {
            kpiGrid.outerHTML = renderKPIs(D.INBOUND_KPIS);
        }
        // Re-render category and source cards (first two glass-cards after KPI grid)
        if (cards.length >= 2 && D.INBOUND_CATEGORIES) {
            cards[0].outerHTML = renderCategories(D.INBOUND_CATEGORIES);
        }
        if (cards.length >= 3 && D.INBOUND_SOURCES) {
            cards[1].outerHTML = renderSources(D.INBOUND_SOURCES);
        }
    };
})();
