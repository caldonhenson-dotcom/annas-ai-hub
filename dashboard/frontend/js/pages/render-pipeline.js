/* ============================================================
   Pipeline & Sales Intelligence — renderer
   Drives all charts, funnels, tables, and leaderboards
   ============================================================ */
(function () {
    'use strict';

    var chartInstances = {};
    var MONTH_SHORT = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

    // Palette for sources / reps
    var PALETTE = ['#3CB4AD','#334FB4','#a78bfa','#34d399','#f472b6','#f59e0b','#60a5fa','#ef4444'];

    // Stage display config
    var STAGE_ORDER = [
        'Inbound Lead',
        'Engaged',
        'First Meeting Booked',
        'Second Meeting Booked',
        'Proposal Shared',
        'Decision Maker Bought-In',
        'Contract Sent',
        'Closed Won',
        'Closed Lost',
        'Disqualified'
    ];

    var STAGE_CSS = {
        'Inbound Lead': 'inbound',
        'Engaged': 'engaged',
        'First Meeting Booked': 'meeting',
        'Second Meeting Booked': 'meeting',
        'Proposal Shared': 'proposal',
        'Decision Maker Bought-In': 'decision',
        'Contract Sent': 'contract',
        'Closed Won': 'won',
        'Closed Lost': 'lost',
        'Disqualified': 'disqualified'
    };

    // Friendly source names
    var SOURCE_LABELS = {
        'OFFLINE': 'Offline / Import',
        'DIRECT_TRAFFIC': 'Direct Traffic',
        'ORGANIC_SEARCH': 'Organic Search',
        'PAID_SEARCH': 'Paid Search',
        'REFERRALS': 'Referrals',
        'SOCIAL_MEDIA': 'Social Media'
    };

    // Known reps (filter out numeric IDs from HubSpot)
    var KNOWN_REPS = [
        'Anna Younger', 'Caldon Henson', 'Jake Heath',
        'James Carberry', 'Josh Elliott', 'Kirill Kopica',
        'Rose Galbally', 'Skye Whitton'
    ];

    // ── Theme helpers ──
    function isDark() { return document.documentElement.getAttribute('data-theme') === 'dark'; }
    function tickCol() { return isDark() ? '#9ca3af' : '#94a3b8'; }
    function tipBg() { return isDark() ? '#1a1d27' : '#242833'; }
    function gridCol() { return isDark() ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)'; }

    // ── Chart helper ──
    function ensureCanvas(containerId, height) {
        var el = document.getElementById(containerId);
        if (!el) return null;
        if (chartInstances[containerId]) {
            chartInstances[containerId].destroy();
            delete chartInstances[containerId];
        }
        el.innerHTML = '';
        el.style.position = 'relative';
        el.style.height = (height || 200) + 'px';
        var canvas = document.createElement('canvas');
        el.appendChild(canvas);
        return canvas;
    }

    // ── Date range for "last 30 days" ──
    function getLast30Range() {
        var now = new Date();
        var start = new Date(now);
        start.setDate(start.getDate() - 30);
        return { start: formatDate(start), end: formatDate(now) };
    }

    // ── Comparison period (previous 30 days before the last 30) ──
    function getPrev30Range() {
        var now = new Date();
        var end = new Date(now);
        end.setDate(end.getDate() - 31);
        var start = new Date(end);
        start.setDate(start.getDate() - 30);
        return { start: formatDate(start), end: formatDate(end) };
    }

    // ================================================================
    // 1. Activity Totals (HubSpot-style comparison cards)
    // ================================================================
    function renderActivityTotals() {
        var el = document.getElementById('pl-activity-totals');
        if (!el) return;

        var current = getLast30Range();
        var previous = getPrev30Range();
        var curAct = getActivityBreakdown(TS.activities_by_type_by_day, current);
        var prevAct = getActivityBreakdown(TS.activities_by_type_by_day, previous);

        var types = [
            { key: 'calls', label: 'Calls', icon: '' },
            { key: 'emails', label: 'Emails', icon: '' },
            { key: 'meetings', label: 'Meetings', icon: '' },
            { key: 'notes', label: 'Notes', icon: '' },
            { key: 'tasks', label: 'Tasks', icon: '' }
        ];

        var html = '';
        types.forEach(function (t) {
            var cur = curAct[t.key] || 0;
            var prev = prevAct[t.key] || 0;
            var pct = prev > 0 ? ((cur - prev) / prev * 100) : (cur > 0 ? 100 : 0);
            var cls = pct > 0 ? 'up' : pct < 0 ? 'down' : 'neutral';
            var arrow = pct > 0 ? '&#9650;' : pct < 0 ? '&#9660;' : '&#9644;';
            html += '<div class="pl-act-card">'
                + '<div class="pl-act-label">' + t.label + '</div>'
                + '<div class="pl-act-value">' + fmtNum(cur) + '</div>'
                + '<span class="pl-act-change ' + cls + '">'
                + arrow + ' ' + Math.abs(pct).toFixed(1) + '%</span>'
                + '</div>';
        });
        el.innerHTML = html;
    }

    // ================================================================
    // 2. Total Leads — monthly bar chart (Chart.js)
    // ================================================================
    function renderLeadsChart() {
        var canvas = ensureCanvas('pl-leads-chart', 200);
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

        chartInstances['pl-leads-chart'] = new Chart(canvas, {
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
        });
    }

    // ================================================================
    // 3. Pipeline Value — monthly bar chart
    // ================================================================
    function renderPipelineChart() {
        var canvas = ensureCanvas('pl-pipeline-chart', 200);
        if (!canvas) return;

        var data = TS.pipeline_value_by_month || {};
        var entries = Object.entries(data).sort();
        if (!entries.length) return;

        var labels = entries.map(function (e) {
            var p = e[0].split('-');
            return MONTH_SHORT[parseInt(p[1], 10) - 1] + ' ' + p[0].slice(2);
        });
        var values = entries.map(function (e) { return e[1]; });

        chartInstances['pl-pipeline-chart'] = new Chart(canvas, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Pipeline',
                    data: values,
                    backgroundColor: '#334FB4CC',
                    hoverBackgroundColor: '#334FB4',
                    borderRadius: 4,
                    barPercentage: 0.7
                }]
            },
            options: chartOpts(true)
        });
    }

    // ================================================================
    // 4. Revenue Won — line chart with trend
    // ================================================================
    function renderRevenueChart() {
        var canvas = ensureCanvas('pl-revenue-chart', 200);
        if (!canvas) return;

        var data = TS.revenue_won_by_month || {};
        var entries = Object.entries(data).sort();
        if (!entries.length) return;

        var labels = entries.map(function (e) {
            var p = e[0].split('-');
            return MONTH_SHORT[parseInt(p[1], 10) - 1] + ' ' + p[0].slice(2);
        });
        var values = entries.map(function (e) { return e[1]; });

        chartInstances['pl-revenue-chart'] = new Chart(canvas, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Revenue Won',
                    data: values,
                    borderColor: '#34d399',
                    backgroundColor: 'rgba(52, 211, 153, 0.15)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 4,
                    pointBackgroundColor: '#34d399',
                    pointHoverRadius: 6,
                    borderWidth: 2
                }]
            },
            options: chartOpts(true)
        });
    }

    // Shared Chart.js options
    function chartOpts(isCurrency) {
        return {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: tipBg(),
                    titleColor: '#fff', bodyColor: '#fff',
                    titleFont: { weight: '600' }, bodyFont: { size: 13 },
                    padding: 10, cornerRadius: 8,
                    callbacks: {
                        label: function (ctx) {
                            var v = ctx.raw;
                            return isCurrency ? '\u00a3' + v.toLocaleString('en-GB') : v.toLocaleString('en-GB');
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
                        callback: function (v) {
                            return isCurrency ? '\u00a3' + fmtNum(v) : fmtNum(v);
                        }
                    }
                },
                x: {
                    grid: { display: false },
                    border: { display: false },
                    ticks: { font: { size: 11, weight: '600' }, color: tickCol() }
                }
            }
        };
    }

    // ================================================================
    // 5. Deal Stage Funnel
    // ================================================================
    function renderFunnel() {
        var el = document.getElementById('pl-funnel');
        if (!el) return;

        // Aggregate deals by stage over last 30 days
        var range = getLast30Range();
        var stageCounts = {};
        var dsm = TS.deals_by_stage_by_month || {};
        for (var month in dsm) {
            if (range === null || (month + '-01' >= range.start && month + '-28' <= range.end)
                || (month + '-01' <= range.end && month + '-28' >= range.start)) {
                var stages = dsm[month];
                for (var stage in stages) {
                    if (!stageCounts[stage]) stageCounts[stage] = 0;
                    stageCounts[stage] += stages[stage].count || 0;
                }
            }
        }

        var maxCount = 0;
        STAGE_ORDER.forEach(function (s) {
            var c = stageCounts[s] || 0;
            if (c > maxCount) maxCount = c;
        });
        if (maxCount === 0) maxCount = 1;

        // Calculate conversion rates
        var html = '<div class="pl-funnel-head">'
            + '<div>Deal Stage</div><div>(Count) Deals</div>'
            + '<div style="text-align:center">Next Step</div>'
            + '<div style="text-align:center">Cumulative</div></div>';

        var totalCreated = 0;
        STAGE_ORDER.forEach(function (s) { totalCreated += (stageCounts[s] || 0); });

        var prevCount = totalCreated;
        STAGE_ORDER.forEach(function (stage) {
            var count = stageCounts[stage] || 0;
            var barPct = Math.max(2, (count / maxCount) * 100);
            var nextPct = prevCount > 0 ? ((count / prevCount) * 100) : 0;
            var cumPct = totalCreated > 0 ? ((count / totalCreated) * 100) : 0;
            var hasPct = count > 0;

            html += '<div class="pl-funnel-row">'
                + '<div class="pl-funnel-stage">' + stage + '</div>'
                + '<div class="pl-funnel-bar-wrap">'
                + '<div class="pl-funnel-bar-track">'
                + '<div class="pl-funnel-bar-fill" style="width:' + barPct.toFixed(1) + '%">'
                + (count > 0 ? count : '') + '</div></div>'
                + '<span class="pl-funnel-bar-label">' + (count > 0 ? count : '0') + '</span></div>'
                + '<div class="pl-funnel-pct' + (hasPct ? '' : ' muted') + '">'
                + (hasPct ? nextPct.toFixed(1) + '%' : '0%') + '</div>'
                + '<div class="pl-funnel-pct' + (hasPct ? '' : ' muted') + '">'
                + (hasPct ? cumPct.toFixed(1) + '%' : '0%') + '</div>'
                + '</div>';

            if (count > 0) prevCount = count;
        });

        el.innerHTML = html;
    }

    // ================================================================
    // 6. Lead Source Report (table with visual bars)
    // ================================================================
    function renderLeadSource() {
        var el = document.getElementById('pl-lead-source');
        if (!el) return;

        // Aggregate all sources (YTD)
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
        if (!total) { el.innerHTML = '<div class="pl-empty">No lead data available</div>'; return; }

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
                + '<td><div class="pl-source-bar" style="width:' + pct.toFixed(1)
                + '%;background:' + color + '"></div></td>'
                + '</tr>';
        });

        // Total row
        html += '<tr class="pl-source-total">'
            + '<td><strong>Total</strong></td>'
            + '<td><strong>' + fmtNum(total) + '</strong></td>'
            + '<td></td><td></td></tr>';

        html += '</tbody></table>';
        el.innerHTML = html;
    }

    // ================================================================
    // 7. Activity Leaderboard by Rep
    // ================================================================
    function renderActivityLeaderboard() {
        var el = document.getElementById('pl-activity-leaderboard');
        if (!el) return;

        // Aggregate rep activities (YTD)
        var reps = {};
        var arm = TS.activities_by_rep_by_month || {};
        var ytdStart = new Date().getFullYear() + '-01';
        for (var month in arm) {
            if (month >= ytdStart) {
                var repData = arm[month];
                for (var rep in repData) {
                    // Skip numeric IDs
                    if (/^\d+$/.test(rep) || rep === 'unassigned') continue;
                    if (!reps[rep]) reps[rep] = { calls: 0, emails: 0, meetings: 0, tasks: 0, notes: 0 };
                    var acts = repData[rep];
                    for (var t in acts) {
                        if (reps[rep].hasOwnProperty(t)) reps[rep][t] += acts[t];
                    }
                }
            }
        }

        var sorted = Object.entries(reps).map(function (e) {
            var total = e[1].calls + e[1].emails + e[1].meetings + e[1].tasks + e[1].notes;
            return { name: e[0], acts: e[1], total: total };
        }).sort(function (a, b) { return b.total - a.total; });

        if (!sorted.length) {
            el.innerHTML = '<div class="pl-empty">No activity data</div>';
            return;
        }

        var html = '<div class="pl-leader-head">'
            + '<div>Rep</div><div style="text-align:center">Calls</div>'
            + '<div style="text-align:center">Emails</div>'
            + '<div style="text-align:center">Meetings</div>'
            + '<div style="text-align:center">Tasks</div>'
            + '<div style="text-align:center">Notes</div>'
            + '<div style="text-align:center">Total</div></div>';

        sorted.forEach(function (rep) {
            var initials = rep.name.split(' ').map(function (w) { return w[0]; }).join('');
            html += '<div class="pl-leader-row">'
                + '<div class="pl-leader-name">'
                + '<span class="pl-leader-avatar">' + initials + '</span>'
                + rep.name + '</div>'
                + '<div class="pl-leader-val">' + (rep.acts.calls || 0) + '</div>'
                + '<div class="pl-leader-val">' + (rep.acts.emails || 0) + '</div>'
                + '<div class="pl-leader-val">' + (rep.acts.meetings || 0) + '</div>'
                + '<div class="pl-leader-val">' + (rep.acts.tasks || 0) + '</div>'
                + '<div class="pl-leader-val">' + (rep.acts.notes || 0) + '</div>'
                + '<div class="pl-leader-total">' + rep.total + '</div>'
                + '</div>';
        });

        el.innerHTML = html;
    }

    // ================================================================
    // 8. Deal Pipeline Table
    // ================================================================
    function renderDealTable() {
        var el = document.getElementById('pl-deal-table');
        if (!el) return;

        // Build deal list from deals_by_stage_by_month (aggregate view)
        var dsm = TS.deals_by_stage_by_month || {};
        var stageData = [];
        for (var month in dsm) {
            var stages = dsm[month];
            for (var stage in stages) {
                var d = stages[stage];
                stageData.push({
                    month: month,
                    stage: stage,
                    count: d.count || 0,
                    value: d.value || 0
                });
            }
        }

        // Sort by month desc, then stage
        stageData.sort(function (a, b) {
            if (b.month !== a.month) return b.month > a.month ? 1 : -1;
            return (STAGE_ORDER.indexOf(a.stage) - STAGE_ORDER.indexOf(b.stage));
        });

        if (!stageData.length) {
            el.innerHTML = '<div class="pl-empty">No deal data</div>';
            return;
        }

        var html = '<table class="pl-deals-table"><thead><tr>'
            + '<th>Month</th><th>Stage</th><th>Deals</th><th>Value</th>'
            + '</tr></thead><tbody>';

        stageData.forEach(function (d) {
            var p = d.month.split('-');
            var monthLabel = MONTH_SHORT[parseInt(p[1], 10) - 1] + ' ' + p[0];
            var cssClass = STAGE_CSS[d.stage] || 'inbound';
            html += '<tr>'
                + '<td>' + monthLabel + '</td>'
                + '<td><span class="pl-deal-stage pl-stage-' + cssClass + '">' + d.stage + '</span></td>'
                + '<td>' + d.count + '</td>'
                + '<td>' + fmtCurrency(d.value) + '</td>'
                + '</tr>';
        });

        html += '</tbody></table>';
        el.innerHTML = html;
    }

    // ================================================================
    // 9. Stale Deals (kept from original — uses STATIC if available)
    // ================================================================
    function renderStaleDealsList() {
        var el = document.getElementById('pl-stale-deals');
        if (!el) return;

        // Use hardcoded stale deals data (from original pipeline)
        var staleDeals = [
            { name: 'GMC - Evri - Rebate', value: 25000, stage: 'Contract Sent', days: 222, owner: 'Caldon Henson' },
            { name: 'The Ayurveda Experience - Freight', value: 60000, stage: 'Engaged', days: 67, owner: 'James Carberry' },
            { name: 'Glow Hub - M&A', value: 10000, stage: 'Engaged', days: 180, owner: 'Josh Elliott' },
            { name: 'MAYAH - Investment', value: 1, stage: 'Contract Sent', days: 42, owner: 'Anna Younger' },
            { name: 'Cascadia Capital - CDD', value: 200000, stage: 'Proposal Shared', days: 76, owner: 'Josh Elliott' },
            { name: 'Nuovaluce Beauty', value: 50000, stage: 'Decision Maker Bought-In', days: 96, owner: 'Anna Younger' },
            { name: 'Finishing Line', value: 40000, stage: 'Engaged', days: 33, owner: 'James Carberry' }
        ];

        var html = '<table class="pl-deals-table"><thead><tr>'
            + '<th>Deal</th><th>Value</th><th>Stage</th><th>Days Stale</th><th>Owner</th>'
            + '</tr></thead><tbody>';

        staleDeals.forEach(function (d) {
            var cssClass = STAGE_CSS[d.stage] || 'inbound';
            html += '<tr>'
                + '<td class="pl-deal-name">' + d.name + '</td>'
                + '<td>' + fmtCurrency(d.value) + '</td>'
                + '<td><span class="pl-deal-stage pl-stage-' + cssClass + '">' + d.stage + '</span></td>'
                + '<td style="font-weight:700;color:' + (d.days > 60 ? 'var(--danger)' : 'var(--warning)') + '">'
                + d.days + 'd</td>'
                + '<td>' + d.owner + '</td>'
                + '</tr>';
        });

        html += '</tbody></table>';
        el.innerHTML = html;
    }

    // ================================================================
    // Master render
    // ================================================================
    window.renderPipeline = function () {
        renderActivityTotals();
        renderLeadsChart();
        renderPipelineChart();
        renderRevenueChart();
        renderFunnel();
        renderLeadSource();
        renderActivityLeaderboard();
        renderDealTable();
        renderStaleDealsList();
    };
})();
