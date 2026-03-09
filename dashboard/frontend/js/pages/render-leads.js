/* ============================================================
   Leads & Conversion — renderer
   KPI cards, trend charts, source tables, marketing funnel
   ============================================================ */
(function () {
    'use strict';

    var MONTH_SHORT = window.MONTH_SHORT;
    var PALETTE = window.PALETTE;

    var SOURCE_LABELS = {
        'OFFLINE': 'Offline / Import',
        'DIRECT_TRAFFIC': 'Direct Traffic',
        'ORGANIC_SEARCH': 'Organic Search',
        'PAID_SEARCH': 'Paid Search',
        'REFERRALS': 'Referrals',
        'SOCIAL_MEDIA': 'Social Media'
    };

    // ── Date helpers ──
    function getLast30Range() {
        var now = new Date();
        var start = new Date(now); start.setDate(start.getDate() - 30);
        return { start: formatDate(start), end: formatDate(now) };
    }
    function getPrev30Range() {
        var now = new Date();
        var end = new Date(now); end.setDate(end.getDate() - 31);
        var start = new Date(end); start.setDate(start.getDate() - 30);
        return { start: formatDate(start), end: formatDate(end) };
    }

    // ================================================================
    // 1. KPI Comparison Cards
    // ================================================================
    function renderKPIs() {
        var el = document.getElementById('ld-kpi-totals');
        if (!el) return;

        var cur = getLast30Range();
        var prev = getPrev30Range();

        var metrics = [
            { label: 'Total Leads', cur: sumDaily(TS.leads_by_day, cur), prev: sumDaily(TS.leads_by_day, prev) },
            { label: 'MQLs', cur: sumDaily(TS.mqls_by_day, cur), prev: sumDaily(TS.mqls_by_day, prev) },
            { label: 'SQLs', cur: sumDaily(TS.sqls_by_day, cur), prev: sumDaily(TS.sqls_by_day, prev) },
            { label: 'Contacts', cur: sumDaily(TS.contacts_created_by_day, cur), prev: sumDaily(TS.contacts_created_by_day, prev) },
            { label: 'Deals Created', cur: sumDaily(TS.deals_created_by_day, cur), prev: sumDaily(TS.deals_created_by_day, prev) }
        ];

        var html = '';
        metrics.forEach(function (m) {
            var pct = m.prev > 0 ? ((m.cur - m.prev) / m.prev * 100) : (m.cur > 0 ? 100 : 0);
            var cls = pct > 0 ? 'up' : pct < 0 ? 'down' : 'neutral';
            var arrow = pct > 0 ? '&#9650;' : pct < 0 ? '&#9660;' : '&#9644;';
            html += '<div class="pl-act-card">'
                + '<div class="pl-act-label">' + m.label + '</div>'
                + '<div class="pl-act-value">' + fmtNum(m.cur) + '</div>'
                + '<span class="pl-act-change ' + cls + '">'
                + arrow + ' ' + Math.abs(pct).toFixed(1) + '% vs prev 30d</span>'
                + '</div>';
        });
        el.innerHTML = html;
    }

    // ================================================================
    // 2. Lead Trend — monthly bar chart (Chart.js)
    // ================================================================
    function renderLeadTrend() {
        var canvas = ensureCanvas('ld-trend-chart', 220);
        if (!canvas) return;

        var monthly = filterDailyToMonthly(TS.leads_by_day, null);
        var entries = Object.entries(monthly).sort();
        if (entries.length > 12) entries = entries.slice(-12);
        if (!entries.length) return;

        var labels = entries.map(function (e) {
            var p = e[0].split('-');
            return MONTH_SHORT[parseInt(p[1], 10) - 1] + ' ' + p[0].slice(2);
        });
        var values = entries.map(function (e) { return e[1]; });

        storeChart('ld-trend-chart', new Chart(canvas, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Leads',
                    data: values,
                    backgroundColor: '#3CB4ADCC',
                    hoverBackgroundColor: '#3CB4AD',
                    borderRadius: 4,
                    barPercentage: 0.7
                }]
            },
            options: chartOpts(false)
        }));
    }

    // ================================================================
    // 3. Leads by Source — table with visual bars
    // ================================================================
    function renderSourceTable() {
        var el = document.getElementById('ld-source-table');
        if (!el) return;

        var sources = {};
        var lsm = TS.leads_by_source_by_month || {};
        var ytdStart = new Date().getFullYear() + '-01';
        for (var month in lsm) {
            if (month >= ytdStart) {
                var srcs = lsm[month];
                for (var src in srcs) {
                    sources[src] = (sources[src] || 0) + srcs[src];
                }
            }
        }

        var sorted = Object.entries(sources).sort(function (a, b) { return b[1] - a[1]; });
        var total = sorted.reduce(function (sum, e) { return sum + e[1]; }, 0);
        if (!total) { el.innerHTML = '<div class="pl-empty">No lead source data</div>'; return; }

        var html = '<table class="pl-source-table"><thead><tr>'
            + '<th>Source</th><th>Count</th><th>Share</th><th>Distribution</th>'
            + '</tr></thead><tbody>';

        sorted.forEach(function (entry, i) {
            var name = SOURCE_LABELS[entry[0]] || entry[0];
            var count = entry[1];
            var pct = (count / total * 100);
            var color = PALETTE[i % PALETTE.length];
            html += '<tr>'
                + '<td><span class="pl-source-name">'
                + '<span class="pl-source-dot" style="background:' + color + '"></span>'
                + name + '</span></td>'
                + '<td>' + fmtNum(count) + '</td>'
                + '<td class="pl-source-pct">' + pct.toFixed(1) + '%</td>'
                + '<td><div class="pl-source-bar" style="width:' + pct.toFixed(1) + '%;background:' + color + '"></div></td>'
                + '</tr>';
        });

        html += '<tr class="pl-source-total"><td><strong>Total</strong></td>'
            + '<td><strong>' + fmtNum(total) + '</strong></td><td></td><td></td></tr>';
        html += '</tbody></table>';
        el.innerHTML = html;
    }

    // ================================================================
    // 4. Lead Status — CSS progress bars
    // ================================================================
    function renderLeadStatus() {
        var el = document.getElementById('ld-status-bars');
        if (!el) return;

        // Derive status from STATIC if available, otherwise show empty
        var statuses = (window.STATIC && window.STATIC.lead_statuses) || {};
        if (!Object.keys(statuses).length) {
            // Fallback: show basic status from TS data
            var cur = getLast30Range();
            var leads = sumDaily(TS.leads_by_day, cur);
            var mqls = sumDaily(TS.mqls_by_day, cur);
            var sqls = sumDaily(TS.sqls_by_day, cur);
            var deals = sumDaily(TS.deals_created_by_day, cur);
            statuses = {
                'New Leads': leads,
                'Marketing Qualified': mqls,
                'Sales Qualified': sqls,
                'Deal Created': deals
            };
        }

        var sorted = Object.entries(statuses).sort(function (a, b) { return b[1] - a[1]; });
        var maxVal = sorted.length ? sorted[0][1] : 1;
        if (maxVal === 0) maxVal = 1;

        var html = '';
        sorted.forEach(function (entry, i) {
            var label = entry[0];
            var val = entry[1];
            var pct = Math.max(2, (val / maxVal) * 100);
            var color = PALETTE[i % PALETTE.length];
            html += '<div style="margin-bottom:8px">'
                + '<div style="display:flex;justify-content:space-between;margin-bottom:4px;font-size:13px">'
                + '<span style="color:var(--text-muted)">' + label + '</span>'
                + '<span style="color:var(--text);font-weight:600">' + fmtNum(val) + '</span></div>'
                + '<div style="height:8px;background:var(--surface2);border-radius:4px;overflow:hidden">'
                + '<div style="height:100%;width:' + pct.toFixed(1) + '%;background:' + color
                + ';border-radius:4px;transition:width 0.6s cubic-bezier(.25,.1,.25,1)"></div></div></div>';
        });
        el.innerHTML = html;
    }

    // ================================================================
    // 5. Contacts Trend — monthly bar chart
    // ================================================================
    function renderContactsTrend() {
        var canvas = ensureCanvas('ld-contacts-chart', 220);
        if (!canvas) return;

        var monthly = filterDailyToMonthly(TS.contacts_created_by_day, null);
        var entries = Object.entries(monthly).sort();
        if (entries.length > 12) entries = entries.slice(-12);
        if (!entries.length) return;

        var labels = entries.map(function (e) {
            var p = e[0].split('-');
            return MONTH_SHORT[parseInt(p[1], 10) - 1] + ' ' + p[0].slice(2);
        });
        var values = entries.map(function (e) { return e[1]; });

        storeChart('ld-contacts-chart', new Chart(canvas, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Contacts Created',
                    data: values,
                    backgroundColor: '#334FB4CC',
                    hoverBackgroundColor: '#334FB4',
                    borderRadius: 4,
                    barPercentage: 0.7
                }]
            },
            options: chartOpts(false)
        }));
    }

    // ================================================================
    // 6. Marketing Funnel — conversion stages with comparison
    // ================================================================
    function renderConversionFunnel() {
        var el = document.getElementById('ld-conversion-funnel');
        if (!el) return;

        var cur = getLast30Range();
        var prev = getPrev30Range();

        var stages = [
            { label: 'Total Leads', cur: sumDaily(TS.leads_by_day, cur), prev: sumDaily(TS.leads_by_day, prev) },
            { label: 'MQLs', cur: sumDaily(TS.mqls_by_day, cur), prev: sumDaily(TS.mqls_by_day, prev) },
            { label: 'SQLs', cur: sumDaily(TS.sqls_by_day, cur), prev: sumDaily(TS.sqls_by_day, prev) },
            { label: 'Deals Created', cur: sumDaily(TS.deals_created_by_day, cur), prev: sumDaily(TS.deals_created_by_day, prev) },
            { label: 'Deals Won', cur: sumDaily(TS.deals_won_by_day, cur), prev: sumDaily(TS.deals_won_by_day, prev) }
        ];

        var maxVal = stages[0].cur || 1;
        var colors = ['#3CB4AD', '#334FB4', '#a78bfa', '#34d399', '#f59e0b'];

        var html = '<div class="pl-funnel-head">'
            + '<div>Stage</div><div>Count</div>'
            + '<div style="text-align:center">Conversion</div>'
            + '<div style="text-align:center">vs Prev 30d</div></div>';

        stages.forEach(function (s, i) {
            var barPct = Math.max(2, (s.cur / (maxVal || 1)) * 100);
            var convPct = i > 0 && stages[i - 1].cur > 0
                ? ((s.cur / stages[i - 1].cur) * 100) : (i === 0 ? 100 : 0);
            var changePct = s.prev > 0 ? ((s.cur - s.prev) / s.prev * 100) : (s.cur > 0 ? 100 : 0);
            var cls = changePct > 0 ? 'up' : changePct < 0 ? 'down' : 'neutral';
            var arrow = changePct > 0 ? '&#9650;' : changePct < 0 ? '&#9660;' : '&#9644;';

            html += '<div class="pl-funnel-row">'
                + '<div class="pl-funnel-stage">' + s.label + '</div>'
                + '<div class="pl-funnel-bar-wrap">'
                + '<div class="pl-funnel-bar-track">'
                + '<div class="pl-funnel-bar-fill" style="width:' + barPct.toFixed(1)
                + '%;background:linear-gradient(90deg,' + colors[i] + ',' + colors[i] + 'CC)">'
                + (s.cur > 0 ? s.cur : '') + '</div></div>'
                + '<span class="pl-funnel-bar-label">' + fmtNum(s.cur) + '</span></div>'
                + '<div class="pl-funnel-pct">' + convPct.toFixed(1) + '%</div>'
                + '<div class="pl-funnel-pct"><span class="pl-act-change ' + cls + '" style="font-size:11px">'
                + arrow + ' ' + Math.abs(changePct).toFixed(1) + '%</span></div>'
                + '</div>';
        });

        el.innerHTML = html;
    }

    // ================================================================
    // 7. Source Effectiveness — detailed table
    // ================================================================
    function renderSourceDetail() {
        var el = document.getElementById('ld-source-detail');
        if (!el) return;

        var sources = {};
        var lsm = TS.leads_by_source_by_month || {};
        for (var month in lsm) {
            var srcs = lsm[month];
            for (var src in srcs) {
                sources[src] = (sources[src] || 0) + srcs[src];
            }
        }

        var mqls = sumDaily(TS.mqls_by_day, null);
        var sorted = Object.entries(sources).sort(function (a, b) { return b[1] - a[1]; });
        var total = sorted.reduce(function (sum, e) { return sum + e[1]; }, 0);
        if (!total) { el.innerHTML = '<div class="pl-empty">No data</div>'; return; }

        var html = '<table class="pl-deals-table"><thead><tr>'
            + '<th>Source</th><th>Leads</th><th>MQLs</th><th>Conv. Rate</th><th>Share</th>'
            + '</tr></thead><tbody>';

        sorted.forEach(function (entry) {
            var name = SOURCE_LABELS[entry[0]] || entry[0];
            var count = entry[1];
            var pct = (count / total * 100);
            // MQL conversion is approximate (no per-source MQL data)
            var mqlEst = Math.round(mqls * (count / total));
            var convRate = count > 0 ? ((mqlEst / count) * 100).toFixed(1) + '%' : '0%';

            html += '<tr>'
                + '<td class="pl-deal-name">' + name + '</td>'
                + '<td>' + fmtNum(count) + '</td>'
                + '<td>' + fmtNum(mqlEst) + '</td>'
                + '<td>' + convRate + '</td>'
                + '<td>' + pct.toFixed(1) + '%</td>'
                + '</tr>';
        });

        html += '</tbody></table>';
        el.innerHTML = html;
    }

    // ================================================================
    // Master render
    // ================================================================
    window.renderLeads = function () {
        renderKPIs();
        renderLeadTrend();
        renderSourceTable();
        renderLeadStatus();
        renderContactsTrend();
        renderConversionFunnel();
        renderSourceDetail();
    };
})();
