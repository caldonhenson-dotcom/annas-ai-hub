/* ============================================================
   Charts — SVG mini-bar, sparkline, monthly bar
   ============================================================ */
(function () {
    'use strict';

    function renderMiniBar(containerId, data, maxItems) {
        var el = document.getElementById(containerId);
        if (!el) return;
        maxItems = maxItems || 8;
        var sorted = Object.entries(data).sort(function(a, b) { return b[1] - a[1]; }).slice(0, maxItems);
        if (sorted.length === 0) { el.innerHTML = '<div style="text-align:center;padding:20px;color:#6b7280;font-size:13px">No data for this period</div>'; return; }
        var maxVal = sorted[0][1] || 1;
        var palette = ['#3CB4AD','#334FB4','#a78bfa','#34d399','#f472b6','#f59e0b','#60a5fa','#ef4444'];
        var html = '';
        sorted.forEach(function(item, i) {
            var label = item[0].length > 20 ? item[0].substring(0, 18) + '..' : item[0];
            var val = item[1];
            var pct = Math.max(2, (val / maxVal) * 100);
            var color = palette[i % palette.length];
            html += '<div style="margin-bottom:5px">'
                + '<div style="display:flex;justify-content:space-between;margin-bottom:3px;font-size:12px">'
                + '<span style="color:#6b7280">' + label + '</span>'
                + '<span style="color:#121212;font-weight:600">' + fmtNum(val) + '</span></div>'
                + '<div style="height:6px;background:#e5e7eb;border-radius:3px;overflow:hidden">'
                + '<div style="height:100%;width:' + pct.toFixed(1) + '%;background:' + color + ';border-radius:3px;'
                + 'transition:width 0.6s cubic-bezier(.25,.1,.25,1)"></div></div></div>';
        });
        el.innerHTML = html;
    }

    function renderSparkline(containerId, data, color) {
        var el = document.getElementById(containerId);
        if (!el) return;
        color = color || '#3CB4AD';
        var entries = Object.entries(data).sort();
        if (entries.length < 2) { el.innerHTML = ''; return; }
        var vals = entries.map(function(e) { return e[1]; });
        var w = 180, h = 36, pad = 2;
        var mn = Math.min.apply(null, vals);
        var mx = Math.max.apply(null, vals);
        var rng = mx - mn || 1;
        var cw = w - pad * 2, ch = h - pad * 2;
        var pts = vals.map(function(v, i) {
            return (pad + (i / (vals.length - 1)) * cw).toFixed(1) + ',' + (pad + ch - ((v - mn) / rng) * ch).toFixed(1);
        });
        var polyline = pts.join(' ');
        var lastPt = pts[pts.length - 1].split(',');
        el.innerHTML = '<svg width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h + '">'
            + '<polyline points="' + polyline + '" fill="none" stroke="' + color + '" stroke-width="2" stroke-linecap="round"/>'
            + '<circle cx="' + lastPt[0] + '" cy="' + lastPt[1] + '" r="3" fill="' + color + '"/>'
            + '</svg>';
    }

    var MONTH_SHORT = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    function renderMonthlyBarChart(containerId, data, color, isCurrency) {
        var el = document.getElementById(containerId);
        if (!el) return;
        color = color || '#3CB4AD';
        var entries = Object.entries(data).sort();
        // Take last 6 months only
        if (entries.length > 6) entries = entries.slice(entries.length - 6);
        if (entries.length === 0) { el.innerHTML = '<span style="color:#64748b;font-size:11px">No data</span>'; return; }
        var vals = entries.map(function(e) { return e[1]; });
        var labels = entries.map(function(e) {
            var parts = e[0].split('-');
            return MONTH_SHORT[parseInt(parts[1], 10) - 1] || e[0];
        });
        var mx = Math.max.apply(null, vals) || 1;
        var w = 260, barH = 90, padTop = 4, padBot = 18, padL = 4, padR = 4;
        var chartH = barH - padTop - padBot;
        var n = entries.length;
        var gap = 6;
        var barW = Math.floor((w - padL - padR - gap * (n - 1)) / n);
        if (barW < 20) barW = 20;
        var totalW = padL + n * barW + (n - 1) * gap + padR;
        var svg = '<svg width="100%" height="' + barH + '" viewBox="0 0 ' + totalW + ' ' + barH + '" preserveAspectRatio="xMidYMid meet">';
        // Axis line
        svg += '<line x1="' + padL + '" y1="' + (padTop + chartH) + '" x2="' + (totalW - padR) + '" y2="' + (padTop + chartH) + '" stroke="#334155" stroke-width="1" opacity="0.3"/>';
        for (var i = 0; i < n; i++) {
            var x = padL + i * (barW + gap);
            var v = vals[i];
            var h = Math.max((v / mx) * chartH, 2);
            var y = padTop + chartH - h;
            // Bar with rounded top
            svg += '<rect x="' + x + '" y="' + y + '" width="' + barW + '" height="' + h + '" rx="3" fill="' + color + '" opacity="0.85"/>';
            // Value inside bar (or above if bar too short)
            var valStr = isCurrency ? (v >= 1000 ? '£' + (v / 1000).toFixed(v >= 10000 ? 0 : 1) + 'k' : '£' + Math.round(v)) : (v >= 1000 ? (v / 1000).toFixed(v >= 10000 ? 0 : 1) + 'k' : String(Math.round(v)));
            var fontSize = barW < 30 ? 9 : 10;
            var textY = h > 18 ? (y + h / 2 + 4) : (y - 3);
            var textColor = h > 18 ? '#fff' : color;
            svg += '<text x="' + (x + barW / 2) + '" y="' + textY + '" text-anchor="middle" fill="' + textColor + '" font-size="' + fontSize + '" font-weight="600" font-family="Assistant,sans-serif">' + valStr + '</text>';
            // Month label below axis
            svg += '<text x="' + (x + barW / 2) + '" y="' + (padTop + chartH + 14) + '" text-anchor="middle" fill="#94a3b8" font-size="10" font-family="Assistant,sans-serif">' + labels[i] + '</text>';
        }
        svg += '</svg>';
        el.innerHTML = svg;
    }


    window.renderMiniBar = renderMiniBar;
    window.renderSparkline = renderSparkline;
    window.renderMonthlyBarChart = renderMonthlyBarChart;
})();
