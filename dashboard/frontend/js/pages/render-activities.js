/* ============================================================
   Activity Tracking — renderer
   KPI cards, doughnut, trend line, rep leaderboard, contacts
   ============================================================ */
(function () {
    'use strict';

    var MONTH_SHORT = window.MONTH_SHORT;
    var PALETTE = window.PALETTE;

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
    // 1. KPI Comparison Cards (6 cards)
    // ================================================================
    function renderKPIs() {
        var el = document.getElementById('act-kpi-totals');
        if (!el) return;

        var cur = getLast30Range();
        var prev = getPrev30Range();
        var curAct = getActivityBreakdown(TS.activities_by_type_by_day, cur);
        var prevAct = getActivityBreakdown(TS.activities_by_type_by_day, prev);
        var curTotal = sumActivitiesDaily(TS.activities_by_type_by_day, cur);
        var prevTotal = sumActivitiesDaily(TS.activities_by_type_by_day, prev);

        var metrics = [
            { label: 'Total', cur: curTotal, prev: prevTotal },
            { label: 'Calls', cur: curAct.calls, prev: prevAct.calls },
            { label: 'Emails', cur: curAct.emails, prev: prevAct.emails },
            { label: 'Meetings', cur: curAct.meetings, prev: prevAct.meetings },
            { label: 'Tasks', cur: curAct.tasks, prev: prevAct.tasks },
            { label: 'Notes', cur: curAct.notes, prev: prevAct.notes }
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
                + arrow + ' ' + Math.abs(pct).toFixed(1) + '%</span>'
                + '</div>';
        });
        el.innerHTML = html;
    }

    // ================================================================
    // 2. Activity Breakdown — Chart.js doughnut
    // ================================================================
    function renderBreakdown() {
        var canvas = ensureCanvas('act-breakdown-chart', 260);
        if (!canvas) return;

        var cur = getLast30Range();
        var breakdown = getActivityBreakdown(TS.activities_by_type_by_day, cur);
        var labels = ['Calls', 'Emails', 'Meetings', 'Tasks', 'Notes'];
        var values = [breakdown.calls, breakdown.emails, breakdown.meetings, breakdown.tasks, breakdown.notes];
        var total = values.reduce(function (s, v) { return s + v; }, 0);
        if (!total) return;

        var colors = ['#3CB4AD', '#334FB4', '#a78bfa', '#34d399', '#f472b6'];

        storeChart('act-breakdown-chart', new Chart(canvas, {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: [{
                    data: values,
                    backgroundColor: colors,
                    hoverBackgroundColor: colors,
                    borderWidth: 2,
                    borderColor: isDark() ? '#1a1d27' : '#fff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '60%',
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            color: isDark() ? '#9ca3af' : '#6b7280',
                            font: { size: 12, weight: '600' },
                            padding: 16,
                            usePointStyle: true,
                            pointStyleWidth: 10
                        }
                    },
                    tooltip: {
                        backgroundColor: tipBg(),
                        titleColor: '#fff', bodyColor: '#fff',
                        padding: 10, cornerRadius: 8,
                        callbacks: {
                            label: function (ctx) {
                                var v = ctx.raw;
                                var pct = total > 0 ? (v / total * 100).toFixed(1) : '0';
                                return ctx.label + ': ' + v.toLocaleString('en-GB') + ' (' + pct + '%)';
                            }
                        }
                    }
                }
            }
        }));
    }

    // ================================================================
    // 3. Activity Trend — Chart.js line (monthly)
    // ================================================================
    function renderTrend() {
        var canvas = ensureCanvas('act-trend-chart', 260);
        if (!canvas) return;

        // Aggregate daily activities into monthly buckets
        var monthly = {};
        var data = TS.activities_by_type_by_day || {};
        for (var day in data) {
            var mk = day.substring(0, 7);
            var counts = data[day];
            var dayTotal = 0;
            for (var t in counts) dayTotal += counts[t];
            monthly[mk] = (monthly[mk] || 0) + dayTotal;
        }

        var entries = Object.entries(monthly).sort();
        if (entries.length > 12) entries = entries.slice(-12);
        if (!entries.length) return;

        var labels = entries.map(function (e) {
            var p = e[0].split('-');
            return MONTH_SHORT[parseInt(p[1], 10) - 1] + ' ' + p[0].slice(2);
        });
        var values = entries.map(function (e) { return e[1]; });

        storeChart('act-trend-chart', new Chart(canvas, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Activities',
                    data: values,
                    borderColor: '#a78bfa',
                    backgroundColor: 'rgba(167, 139, 250, 0.15)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 4,
                    pointBackgroundColor: '#a78bfa',
                    pointHoverRadius: 6,
                    borderWidth: 2
                }]
            },
            options: chartOpts(false)
        }));
    }

    // ================================================================
    // 4. Activity Leaderboard by Rep
    // ================================================================
    function renderLeaderboard() {
        var el = document.getElementById('act-leaderboard');
        if (!el) return;

        var reps = {};
        var arm = TS.activities_by_rep_by_month || {};
        var ytdStart = new Date().getFullYear() + '-01';
        for (var month in arm) {
            if (month >= ytdStart) {
                var repData = arm[month];
                for (var rep in repData) {
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
    // 5. Contacts Overview — KPI mini-cards
    // ================================================================
    function renderContacts() {
        var el = document.getElementById('act-contacts-overview');
        if (!el) return;

        var cur = getLast30Range();
        var contacts30 = sumDaily(TS.contacts_created_by_day, cur);
        var contactsAll = sumDaily(TS.contacts_created_by_day, null);
        var companies = (window.STATIC && window.STATIC.companies_total) || 0;

        var items = [
            { label: 'Total Contacts', value: fmtNum(contactsAll), color: '#3CB4AD' },
            { label: 'New (30d)', value: fmtNum(contacts30), color: '#334FB4' },
            { label: 'Companies', value: fmtNum(companies), color: '#a78bfa' }
        ];

        var html = '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:16px">';
        items.forEach(function (item) {
            html += '<div style="text-align:center;padding:12px;background:var(--surface2);border-radius:var(--radius)">'
                + '<div style="font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.04em;margin-bottom:4px">'
                + item.label + '</div>'
                + '<div style="font-family:var(--font-display);font-size:20px;font-weight:400;color:' + item.color + '">'
                + item.value + '</div></div>';
        });
        html += '</div>';

        // Contact creation trend sparkline
        var monthly = filterDailyToMonthly(TS.contacts_created_by_day, null);
        var entries = Object.entries(monthly).sort().slice(-6);
        if (entries.length) {
            html += '<div style="font-size:12px;font-weight:600;color:var(--text-muted);margin-bottom:8px">Recent Contact Creation</div>';
            var maxVal = Math.max.apply(null, entries.map(function (e) { return e[1]; })) || 1;
            entries.forEach(function (entry, i) {
                var p = entry[0].split('-');
                var label = MONTH_SHORT[parseInt(p[1], 10) - 1] + ' ' + p[0].slice(2);
                var pct = Math.max(2, (entry[1] / maxVal) * 100);
                html += '<div style="margin-bottom:5px">'
                    + '<div style="display:flex;justify-content:space-between;margin-bottom:3px;font-size:12px">'
                    + '<span style="color:var(--text-muted)">' + label + '</span>'
                    + '<span style="color:var(--text);font-weight:600">' + fmtNum(entry[1]) + '</span></div>'
                    + '<div style="height:6px;background:var(--surface2);border-radius:3px;overflow:hidden">'
                    + '<div style="height:100%;width:' + pct.toFixed(1) + '%;background:' + PALETTE[i % PALETTE.length]
                    + ';border-radius:3px;transition:width 0.6s cubic-bezier(.25,.1,.25,1)"></div></div></div>';
            });
        }

        el.innerHTML = html;
    }

    // ================================================================
    // 6. Monthly Breakdown by Type — stacked bar chart
    // ================================================================
    function renderTypeStacked() {
        var canvas = ensureCanvas('act-type-stacked', 260);
        if (!canvas) return;

        var data = TS.activities_by_type_by_day || {};
        var monthly = {};
        for (var day in data) {
            var mk = day.substring(0, 7);
            if (!monthly[mk]) monthly[mk] = { calls: 0, emails: 0, meetings: 0, tasks: 0, notes: 0 };
            var counts = data[day];
            for (var t in counts) {
                if (monthly[mk].hasOwnProperty(t)) monthly[mk][t] += counts[t];
            }
        }

        var entries = Object.entries(monthly).sort();
        if (entries.length > 6) entries = entries.slice(-6);
        if (!entries.length) return;

        var labels = entries.map(function (e) {
            var p = e[0].split('-');
            return MONTH_SHORT[parseInt(p[1], 10) - 1] + ' ' + p[0].slice(2);
        });

        var types = ['calls', 'emails', 'meetings', 'tasks', 'notes'];
        var colors = ['#3CB4AD', '#334FB4', '#a78bfa', '#34d399', '#f472b6'];
        var datasets = types.map(function (type, i) {
            return {
                label: type.charAt(0).toUpperCase() + type.slice(1),
                data: entries.map(function (e) { return e[1][type] || 0; }),
                backgroundColor: colors[i] + 'CC',
                hoverBackgroundColor: colors[i],
                borderRadius: 2,
                barPercentage: 0.7
            };
        });

        storeChart('act-type-stacked', new Chart(canvas, {
            type: 'bar',
            data: { labels: labels, datasets: datasets },
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
                            usePointStyle: true,
                            pointStyleWidth: 10
                        }
                    },
                    tooltip: {
                        backgroundColor: tipBg(),
                        titleColor: '#fff', bodyColor: '#fff',
                        padding: 10, cornerRadius: 8
                    }
                },
                scales: {
                    x: {
                        stacked: true,
                        grid: { display: false },
                        border: { display: false },
                        ticks: { font: { size: 11, weight: '600' }, color: tickCol() }
                    },
                    y: {
                        stacked: true,
                        beginAtZero: true,
                        grid: { color: gridCol() },
                        border: { display: false },
                        ticks: {
                            font: { size: 11 },
                            color: tickCol(),
                            callback: function (v) { return fmtNum(v); }
                        }
                    }
                }
            }
        }));
    }

    // ================================================================
    // Master render
    // ================================================================
    window.renderActivities = function () {
        renderKPIs();
        renderBreakdown();
        renderTrend();
        renderLeaderboard();
        renderContacts();
        renderTypeStacked();
    };
})();
