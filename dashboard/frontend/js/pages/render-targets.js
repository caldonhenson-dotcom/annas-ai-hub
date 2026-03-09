/* ============================================================
   Targets & Reverse Engineering — renderer
   Target progress, gap analysis, requirements, what-if
   ============================================================ */
(function () {
    'use strict';

    var MONTH_SHORT = window.MONTH_SHORT;
    var PALETTE = window.PALETTE;

    // Target config (editable — could later come from config/API)
    var TARGETS = {
        monthly: 100000,
        quarterly: 300000,
        annual: 1200000,
        mql_rate: 0.05,
        sql_rate: 0.5,
        opp_rate: 0.5,
        win_rate: 0.27,
        avg_deal: 15714
    };

    // ================================================================
    // 1. KPI Cards
    // ================================================================
    function renderKPIs() {
        var el = document.getElementById('tgt-kpi-totals');
        if (!el) return;

        var now = new Date();
        var ytdRange = { start: now.getFullYear() + '-01-01', end: formatDate(now) };
        var wonYTD = sumDaily(TS.deals_won_value_by_day, ytdRange);
        var dealsWon = sumDaily(TS.deals_won_by_day, ytdRange);

        // Pipeline total
        var pvm = TS.pipeline_value_by_month || {};
        var totalPipeline = 0;
        for (var m in pvm) totalPipeline += pvm[m];

        var pctOfTarget = TARGETS.annual > 0 ? (wonYTD / TARGETS.annual * 100) : 0;
        var pctColor = pctOfTarget >= 80 ? 'var(--success)' : pctOfTarget >= 50 ? 'var(--warning)' : 'var(--danger)';

        var cards = [
            { label: 'Monthly Target', value: fmtCurrency(TARGETS.monthly) },
            { label: 'Quarterly Target', value: fmtCurrency(TARGETS.quarterly) },
            { label: 'Annual Target', value: fmtCurrency(TARGETS.annual) },
            { label: 'Won YTD', value: fmtCurrency(wonYTD), sub: dealsWon + ' deals' },
            { label: 'Pipeline', value: fmtCurrency(totalPipeline), sub: pctOfTarget.toFixed(1) + '% of target' }
        ];

        var html = '';
        cards.forEach(function (c) {
            html += '<div class="pl-act-card">'
                + '<div class="pl-act-label">' + c.label + '</div>'
                + '<div class="pl-act-value">' + c.value + '</div>'
                + (c.sub ? '<span style="font-size:11px;color:var(--text-muted);margin-top:2px">' + c.sub + '</span>' : '')
                + '</div>';
        });
        el.innerHTML = html;
    }

    // ================================================================
    // 2. Target Progress — line chart (cumulative revenue vs target line)
    // ================================================================
    function renderProgressChart() {
        var canvas = ensureCanvas('tgt-progress-chart', 260);
        if (!canvas) return;

        var rwm = TS.revenue_won_by_month || {};
        var entries = Object.keys(rwm).sort();
        if (!entries.length) {
            canvas.parentElement.innerHTML = '<div class="pl-empty">No revenue data</div>';
            return;
        }

        var labels = entries.map(function (m) {
            var p = m.split('-');
            return MONTH_SHORT[parseInt(p[1], 10) - 1] + ' ' + p[0].slice(2);
        });

        // Cumulative actual
        var cumulative = [];
        var runningTotal = 0;
        entries.forEach(function (m) {
            runningTotal += (rwm[m] || 0);
            cumulative.push(runningTotal);
        });

        // Target line (linear)
        var targetLine = entries.map(function (m, i) {
            return TARGETS.monthly * (i + 1);
        });

        storeChart('tgt-progress-chart', new Chart(canvas, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Actual (Cumulative)',
                        data: cumulative,
                        borderColor: '#34d399',
                        backgroundColor: 'rgba(52, 211, 153, 0.1)',
                        fill: true,
                        tension: 0.3,
                        pointRadius: 4,
                        pointBackgroundColor: '#34d399',
                        borderWidth: 2.5
                    },
                    {
                        label: 'Target',
                        data: targetLine,
                        borderColor: '#ef4444',
                        borderDash: [6, 3],
                        pointRadius: 0,
                        borderWidth: 2,
                        fill: false
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            color: tickCol(),
                            font: { size: 11, weight: '600' },
                            padding: 12,
                            usePointStyle: true
                        }
                    },
                    tooltip: {
                        backgroundColor: tipBg(),
                        titleColor: '#fff', bodyColor: '#fff',
                        padding: 10, cornerRadius: 8,
                        callbacks: {
                            label: function (ctx) {
                                return ctx.dataset.label + ': \u00a3' + ctx.raw.toLocaleString('en-GB');
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: { color: gridCol() },
                        border: { display: false },
                        ticks: {
                            font: { size: 11 }, color: tickCol(),
                            callback: function (v) { return '\u00a3' + fmtNum(v); }
                        }
                    },
                    x: {
                        grid: { display: false },
                        border: { display: false },
                        ticks: { font: { size: 11, weight: '600' }, color: tickCol() }
                    }
                }
            }
        }));
    }

    // ================================================================
    // 3. Required vs Actual — visual grid
    // ================================================================
    function renderRequiredActual() {
        var el = document.getElementById('tgt-required-actual');
        if (!el) return;

        var now = new Date();
        var ytdRange = { start: now.getFullYear() + '-01-01', end: formatDate(now) };
        var leads = sumDaily(TS.leads_by_day, ytdRange);
        var mqls = sumDaily(TS.mqls_by_day, ytdRange);
        var sqls = sumDaily(TS.sqls_by_day, ytdRange);
        var dealsCreated = sumDaily(TS.deals_created_by_day, ytdRange);
        var dealsWon = sumDaily(TS.deals_won_by_day, ytdRange);

        // Reverse engineer required numbers
        var reqDeals = Math.ceil(TARGETS.annual / TARGETS.avg_deal);
        var reqOpps = Math.ceil(reqDeals / TARGETS.win_rate);
        var reqSQLs = Math.ceil(reqOpps / TARGETS.opp_rate);
        var reqMQLs = Math.ceil(reqSQLs / TARGETS.sql_rate);
        var reqLeads = TARGETS.mql_rate > 0 ? Math.ceil(reqMQLs / TARGETS.mql_rate) : 0;

        var metrics = [
            { label: 'Leads', required: reqLeads, actual: leads, color: '#3CB4AD' },
            { label: 'MQLs', required: reqMQLs, actual: mqls, color: '#334FB4' },
            { label: 'SQLs', required: reqSQLs, actual: sqls, color: '#a78bfa' },
            { label: 'Opps', required: reqOpps, actual: dealsCreated, color: '#f472b6' },
            { label: 'Deals', required: reqDeals, actual: dealsWon, color: '#34d399' }
        ];

        var html = '<div style="display:grid;grid-template-columns:repeat(5,1fr);gap:8px">';
        metrics.forEach(function (m) {
            var gap = m.actual - m.required;
            var gapColor = gap >= 0 ? 'var(--success)' : 'var(--danger)';
            var gapSign = gap >= 0 ? '+' : '';
            html += '<div style="text-align:center;padding:10px">'
                + '<div style="font-size:10px;text-transform:uppercase;letter-spacing:0.04em;color:var(--text-muted);margin-bottom:4px">' + m.label + '</div>'
                + '<div style="font-size:20px;font-weight:800;color:' + m.color + '">' + fmtNum(m.required) + '</div>'
                + '<div style="font-size:11px;color:var(--text-muted)">required</div>'
                + '<div style="font-size:14px;font-weight:700;color:var(--text);margin-top:4px">' + fmtNum(m.actual) + '</div>'
                + '<div style="font-size:11px;color:' + gapColor + ';font-weight:600">' + gapSign + fmtNum(gap) + ' gap</div>'
                + '</div>';
        });
        html += '</div>';
        el.innerHTML = html;
    }

    // ================================================================
    // 4. Gap Analysis
    // ================================================================
    function renderGapAnalysis() {
        var el = document.getElementById('tgt-gap-analysis');
        if (!el) return;

        var now = new Date();
        var ytdRange = { start: now.getFullYear() + '-01-01', end: formatDate(now) };
        var wonRev = sumDaily(TS.deals_won_value_by_day, ytdRange);
        var leads = sumDaily(TS.leads_by_day, ytdRange);
        var mqls = sumDaily(TS.mqls_by_day, ytdRange);
        var sqls = sumDaily(TS.sqls_by_day, ytdRange);

        var pvm = TS.pipeline_value_by_month || {};
        var pipeline = 0;
        for (var m in pvm) pipeline += pvm[m];

        var gaps = [
            { label: 'Revenue Gap', value: wonRev - TARGETS.annual },
            { label: 'Pipeline vs Target', value: pipeline - TARGETS.annual },
            { label: 'MQLs Gap Annual', value: mqls },
            { label: 'SQLs Gap Annual', value: sqls }
        ];

        var html = '';
        gaps.forEach(function (g) {
            var color = g.value >= 0 ? 'var(--success)' : 'var(--danger)';
            var prefix = g.value >= 0 ? '+' : '';
            var displayVal = Math.abs(g.value) >= 1000 ? prefix + fmtCurrency(g.value) : prefix + fmtNum(g.value);
            html += '<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--card-border);font-size:13px">'
                + '<span style="color:var(--text-muted)">' + g.label + '</span>'
                + '<span style="color:' + color + ';font-weight:600">' + displayVal + '</span></div>';
        });
        el.innerHTML = html;
    }

    // ================================================================
    // 5. Daily / Weekly Requirements
    // ================================================================
    function renderRequirements() {
        var el = document.getElementById('tgt-requirements');
        if (!el) return;

        var reqDeals = Math.ceil(TARGETS.annual / TARGETS.avg_deal);
        var reqOpps = Math.ceil(reqDeals / TARGETS.win_rate);
        var reqSQLs = Math.ceil(reqOpps / TARGETS.opp_rate);
        var reqMQLs = Math.ceil(reqSQLs / TARGETS.sql_rate);
        var reqLeads = TARGETS.mql_rate > 0 ? Math.ceil(reqMQLs / TARGETS.mql_rate) : 0;
        var workDays = 260;
        var workWeeks = 52;

        var items = [
            { label: 'Daily Leads', value: (reqLeads / workDays).toFixed(1) },
            { label: 'Daily MQLs', value: (reqMQLs / workDays).toFixed(1) },
            { label: 'Daily SQLs', value: (reqSQLs / workDays).toFixed(1) },
            { label: 'Daily Deals to Close', value: (reqDeals / workDays).toFixed(1) },
            { label: 'Weekly Leads', value: (reqLeads / workWeeks).toFixed(1) },
            { label: 'Weekly MQLs', value: (reqMQLs / workWeeks).toFixed(1) },
            { label: 'Weekly SQLs', value: (reqSQLs / workWeeks).toFixed(1) },
            { label: 'Weekly Deals to Close', value: (reqDeals / workWeeks).toFixed(1) }
        ];

        var html = '';
        items.forEach(function (item) {
            html += '<div style="display:flex;justify-content:space-between;padding:5px 0;font-size:13px;border-bottom:1px solid var(--card-border)">'
                + '<span style="color:var(--text-muted)">' + item.label + '</span>'
                + '<span style="color:var(--text);font-weight:600">' + item.value + '</span></div>';
        });
        el.innerHTML = html;
    }

    // ================================================================
    // 6. What-If Scenarios
    // ================================================================
    function renderWhatIf() {
        var el = document.getElementById('tgt-whatif');
        if (!el) return;

        var baseRate = TARGETS.mql_rate;
        var leads = sumDaily(TS.leads_by_day, null);
        var scenarios = [10, 20, 30, 50];

        var html = '<table class="pl-deals-table"><thead><tr>'
            + '<th>Improvement</th><th>New MQL Rate</th><th>Additional MQLs</th><th>Est. Revenue Impact</th>'
            + '</tr></thead><tbody>';

        scenarios.forEach(function (pct) {
            var newRate = baseRate * (1 + pct / 100);
            var currentMQLs = leads * baseRate;
            var newMQLs = leads * newRate;
            var additional = Math.round(newMQLs - currentMQLs);
            var revImpact = additional * TARGETS.sql_rate * TARGETS.opp_rate * TARGETS.win_rate * TARGETS.avg_deal;

            html += '<tr>'
                + '<td class="pl-deal-name">+' + pct + '%</td>'
                + '<td>' + (newRate * 100).toFixed(1) + '%</td>'
                + '<td>' + fmtNum(additional) + '</td>'
                + '<td>' + fmtCurrency(revImpact) + '</td>'
                + '</tr>';
        });

        html += '</tbody></table>';
        el.innerHTML = html;
    }

    // ================================================================
    // Master render
    // ================================================================
    window.renderTargets = function () {
        renderKPIs();
        renderProgressChart();
        renderRequiredActual();
        renderGapAnalysis();
        renderRequirements();
        renderWhatIf();
    };
})();
