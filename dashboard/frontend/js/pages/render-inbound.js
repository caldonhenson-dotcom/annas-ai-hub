/* ============================================================
   Render — Inbound Queue KPI + category + source cards
   ============================================================ */
(function () {
    'use strict';

    var D = window.STATIC;
    var esc = window.escHtml || function (s) { return s; };

    function renderKPIs(kpis) {
        var html = '<div class="kpi-grid" style="grid-template-columns:repeat(4,1fr)">';
        kpis.forEach(function (k) {
            html += '<div class="stat-card" style="--accent:' + k.accent + '">'
                + '<div style="width:22px;height:22px;border-radius:5px;'
                + 'background:linear-gradient(135deg,' + k.accent + '22,' + k.accent + '11);'
                + 'display:flex;align-items:center;justify-content:center;'
                + 'font-size:11px;flex-shrink:0;margin-bottom:2px;'
                + 'border:1px solid ' + k.accent + '33">' + k.icon + '</div>'
                + '<div class="text-muted-xs" style="text-transform:uppercase;letter-spacing:0.05em;margin-bottom:1px">'
                + esc(k.label) + '</div>'
                + '<div data-role="stat-value" style="font-size:17px;font-weight:800;color:var(--text);'
                + 'line-height:1.1;margin-bottom:1px">' + k.value + '</div>'
                + '<div class="text-muted-sm">' + esc(k.subtitle) + '</div>'
                + '</div>';
        });
        return html + '</div>';
    }

    function renderCategories(cats) {
        var html = '<div class="glass-card"><div class="card-title">Signal Categories</div>'
            + '<div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:6px">';
        cats.forEach(function (c) {
            html += '<span style="font-size:11px;font-weight:600;color:' + c.color + ';'
                + 'background:' + c.color + '12;padding:4px 10px;border-radius:6px;'
                + 'border:1px solid ' + c.color + '30">'
                + esc(c.label) + ': ' + c.count + '</span>';
        });
        return html + '</div></div>';
    }

    function renderSources(sources) {
        var html = '<div class="glass-card"><div class="card-title">By Source</div>'
            + '<div style="display:flex;gap:16px;margin-top:6px">';
        sources.forEach(function (s) {
            html += '<div style="text-align:center;padding:10px 16px;background:var(--surface2);'
                + 'border-radius:8px;flex:1;min-width:80px">'
                + '<div style="font-size:18px">' + s.icon + '</div>'
                + '<div style="font-size:18px;font-weight:700;color:var(--text);margin:4px 0">' + s.count + '</div>'
                + '<div class="text-muted-xs" style="text-transform:capitalize">' + esc(s.label) + '</div>'
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
