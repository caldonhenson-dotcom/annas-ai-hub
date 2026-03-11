/* ============================================================
   Pipeline — Deals renderer (Table / Report / Gantt)
   Loads real HubSpot deal data from hubspot-deals.json
   ============================================================ */
(function () {
    'use strict';

    var DEALS = [];
    var FILTERED = [];
    var SORT_KEY = 'created';
    var SORT_DIR = 'desc';
    var ACTIVE_PERIOD = 'ytd';
    var ACTIVE_VIEW = 'table';
    var HUB_DOMAIN = 'app-eu1.hubspot.com';
    var HUB_ID = '26931451';

    var STAGE_ORDER = [
        'Qualified Lead', 'Engaged', 'First Meeting Booked',
        'Second Meeting Booked', 'Proposal Shared',
        'Decision Maker Bought-In', 'Contract Sent',
        'Closed Won', 'Closed Lost', 'Disqualified', 'Re-engage'
    ];

    var STAGE_CSS = {
        'Qualified Lead': 'qualified', 'Engaged': 'engaged',
        'First Meeting Booked': 'meeting', 'Second Meeting Booked': 'meeting',
        'Proposal Shared': 'proposal', 'Decision Maker Bought-In': 'decision',
        'Contract Sent': 'contract', 'Closed Won': 'won',
        'Closed Lost': 'lost', 'Disqualified': 'disqualified',
        'Re-engage': 'reengage'
    };

    var STAGE_COLOURS = {
        'Qualified Lead': '#6b7280', 'Engaged': '#3CB4AD',
        'First Meeting Booked': '#3b82f6', 'Second Meeting Booked': '#3b82f6',
        'Proposal Shared': '#8b5cf6', 'Decision Maker Bought-In': '#f59e0b',
        'Contract Sent': '#10b981', 'Closed Won': '#22c55e',
        'Closed Lost': '#ef4444', 'Disqualified': '#6b7280',
        'Re-engage': '#f59e0b'
    };

    var MONTH_SHORT = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

    // ── Helpers ──
    function fmtCurrency(v) {
        if (v === null || v === undefined) return '—';
        return '£' + Number(v).toLocaleString('en-GB', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
    }
    function fmtCurrencyK(v) {
        if (v >= 1000000) return '£' + (v / 1000000).toFixed(2) + 'M';
        if (v >= 1000) return '£' + (v / 1000).toFixed(2) + 'K';
        return fmtCurrency(v);
    }
    function fmtDate(iso) {
        if (!iso) return '—';
        var d = new Date(iso);
        return d.getDate() + ' ' + MONTH_SHORT[d.getMonth()] + ' ' + d.getFullYear();
    }
    function fmtDateShort(iso) {
        if (!iso) return '—';
        var d = new Date(iso);
        return d.getDate() + ' ' + MONTH_SHORT[d.getMonth()] + ' ' + String(d.getFullYear()).slice(2);
    }
    function daysBetween(a, b) {
        return Math.round(Math.abs(new Date(b) - new Date(a)) / 86400000);
    }
    function initials(name) {
        if (!name) return '?';
        return name.split(' ').map(function (w) { return w[0] || ''; }).join('').toUpperCase();
    }

    // ── Period Filter ──
    function getPeriodRange(period) {
        var now = new Date();
        var y = now.getFullYear();
        var m = now.getMonth();
        if (period === '30d') {
            var start = new Date(now); start.setDate(start.getDate() - 30);
            return { start: start, end: now };
        }
        if (period === 'mtd') return { start: new Date(y, m, 1), end: now };
        if (period === 'ytd') return { start: new Date(y, 0, 1), end: now };
        return null; // all
    }

    function filterByPeriod(deals, period) {
        var range = getPeriodRange(period);
        if (!range) return deals;
        return deals.filter(function (d) {
            var created = new Date(d.created);
            return created >= range.start && created <= range.end;
        });
    }

    // ── Apply All Filters ──
    function applyFilters() {
        var owner = document.getElementById('pl-filter-owner');
        var product = document.getElementById('pl-filter-product');
        var source = document.getElementById('pl-filter-source');
        var stage = document.getElementById('pl-filter-stage');
        var ov = owner ? owner.value : '';
        var pv = product ? product.value : '';
        var sv = source ? source.value : '';
        var stv = stage ? stage.value : '';

        FILTERED = filterByPeriod(DEALS, ACTIVE_PERIOD);
        if (ov) FILTERED = FILTERED.filter(function (d) { return d.owner === ov; });
        if (pv) FILTERED = FILTERED.filter(function (d) { return d.product.indexOf(pv) !== -1; });
        if (sv) FILTERED = FILTERED.filter(function (d) { return d.source === sv; });
        if (stv) FILTERED = FILTERED.filter(function (d) { return d.stage === stv; });

        sortDeals();
        renderAll();
    }

    function sortDeals() {
        FILTERED.sort(function (a, b) {
            var va = a[SORT_KEY] || '';
            var vb = b[SORT_KEY] || '';
            if (SORT_KEY === 'amount' || SORT_KEY === 'weighted') {
                va = Number(va) || 0; vb = Number(vb) || 0;
            }
            if (va < vb) return SORT_DIR === 'asc' ? -1 : 1;
            if (va > vb) return SORT_DIR === 'asc' ? 1 : -1;
            return 0;
        });
    }

    // ================================================================
    // YoY Helpers
    // ================================================================
    function getYoYPeriod(period) {
        var now = new Date();
        var y = now.getFullYear() - 1;
        var m = now.getMonth();
        if (period === '30d') {
            var s = new Date(now); s.setDate(s.getDate() - 30);
            var ps = new Date(s); ps.setFullYear(ps.getFullYear() - 1);
            var pe = new Date(now); pe.setFullYear(pe.getFullYear() - 1);
            return { start: ps, end: pe };
        }
        if (period === 'mtd') return { start: new Date(y, m, 1), end: new Date(y, m, now.getDate()) };
        if (period === 'ytd') return { start: new Date(y, 0, 1), end: new Date(y, m, now.getDate()) };
        return null;
    }

    function calcYoY(current, previous) {
        if (!previous || previous === 0) return current > 0 ? { pct: 100, cls: 'up', arrow: '&#9650;' } : { pct: 0, cls: 'flat', arrow: '&#9644;' };
        var pct = ((current - previous) / previous * 100);
        var cls = pct > 0 ? 'up' : pct < 0 ? 'down' : 'flat';
        var arrow = pct > 0 ? '&#9650;' : pct < 0 ? '&#9660;' : '&#9644;';
        return { pct: Math.abs(pct).toFixed(1), cls: cls, arrow: arrow };
    }

    function yoyBadge(yoy) {
        if (!yoy) return '';
        return '<span class="pl-yoy ' + yoy.cls + '">' + yoy.arrow + ' ' + yoy.pct + '% YoY</span>';
    }

    function calcPeriodMetrics(deals) {
        var now = new Date();
        var r = { total: 0, weighted: 0, open: 0, won: 0, lost: 0, count: deals.length, wonCount: 0, lostCount: 0, openCount: 0, age: 0 };
        deals.forEach(function (d) {
            r.total += d.amount; r.weighted += d.weighted;
            if (d.isWon) { r.won += d.amount; r.wonCount++; }
            else if (d.isLost) { r.lost += d.amount; r.lostCount++; }
            else { r.open += d.amount; r.openCount++; r.age += daysBetween(d.created, now); }
        });
        r.avgAge = r.openCount > 0 ? (r.age / r.openCount / 30).toFixed(1) : '0';
        return r;
    }

    // ================================================================
    // Summary Cards (with YoY)
    // ================================================================
    function renderSummary() {
        var el = document.getElementById('pl-summary-row');
        if (!el) return;

        var cur = calcPeriodMetrics(FILTERED);
        var yoyRange = getYoYPeriod(ACTIVE_PERIOD);
        var prevDeals = yoyRange ? DEALS.filter(function (d) {
            var c = new Date(d.created);
            return c >= yoyRange.start && c <= yoyRange.end;
        }) : [];
        var prev = calcPeriodMetrics(prevDeals);
        var hasYoY = prevDeals.length > 0 && ACTIVE_PERIOD !== 'all';

        var avgDeal = cur.count > 0 ? cur.total / cur.count : 0;
        var yTotal = hasYoY ? calcYoY(cur.total, prev.total) : null;
        var yWeighted = hasYoY ? calcYoY(cur.weighted, prev.weighted) : null;
        var yOpen = hasYoY ? calcYoY(cur.open, prev.open) : null;
        var yWon = hasYoY ? calcYoY(cur.won, prev.won) : null;
        var yLost = hasYoY ? calcYoY(cur.lost, prev.lost) : null;
        var yCount = hasYoY ? calcYoY(cur.count, prev.count) : null;

        var cards = [
            { label: 'Total Deal Amount', value: fmtCurrencyK(cur.total), sub: 'Avg ' + fmtCurrencyK(avgDeal) + ' per deal', yoy: yTotal },
            { label: 'Weighted Amount', value: fmtCurrencyK(cur.weighted), sub: cur.count + ' deals' + (hasYoY ? ' (was ' + prev.count + ')' : ''), yoy: yWeighted },
            { label: 'Open Deal Amount', value: fmtCurrencyK(cur.open), sub: cur.openCount + ' open deals', yoy: yOpen },
            { label: 'Closed Won', value: fmtCurrencyK(cur.won), sub: cur.wonCount + ' won', cls: 'color:var(--success)', yoy: yWon },
            { label: 'Closed Lost', value: fmtCurrencyK(cur.lost), sub: cur.lostCount + ' lost', cls: 'color:var(--danger)', yoy: yLost },
            { label: 'Avg Deal Age', value: cur.avgAge + ' mo', sub: 'Open deals', yoy: null }
        ];

        var html = '';
        cards.forEach(function (c) {
            html += '<div class="pl-sum-card">'
                + '<div class="pl-sum-label">' + c.label + '</div>'
                + '<div class="pl-sum-value"' + (c.cls ? ' style="' + c.cls + '"' : '') + '>' + c.value + '</div>'
                + '<div class="pl-sum-sub">' + c.sub + '</div>'
                + (c.yoy ? yoyBadge(c.yoy) : '')
                + '</div>';
        });
        el.innerHTML = html;
    }

    // ================================================================
    // Department Breakdown
    // ================================================================
    function renderDeptBreakdown() {
        var grid = document.getElementById('pl-dept-grid');
        if (!grid) return;

        var depts = {};
        FILTERED.forEach(function (d) {
            var prods = d.product ? d.product.split(';') : ['Unassigned'];
            prods.forEach(function (p) {
                p = p.trim() || 'Unassigned';
                if (!depts[p]) depts[p] = { count: 0, amount: 0, won: 0, lost: 0, open: 0, wonCount: 0 };
                depts[p].count++;
                depts[p].amount += d.amount;
                if (d.isWon) { depts[p].won += d.amount; depts[p].wonCount++; }
                else if (d.isLost) depts[p].lost += d.amount;
                else depts[p].open += d.amount;
            });
        });

        var order = ['CDD', 'DIS', 'DIS Lite', 'Supply Chain', 'Delivery', 'M&A', 'Unassigned'];
        var sorted = order.filter(function (k) { return depts[k]; });
        // Add any not in order
        Object.keys(depts).forEach(function (k) { if (sorted.indexOf(k) === -1) sorted.push(k); });

        var html = '';
        sorted.forEach(function (name) {
            var d = depts[name];
            var winRate = (d.wonCount + (d.count - d.wonCount - (d.count - d.wonCount))) > 0
                ? (d.wonCount / d.count * 100).toFixed(0) : '0';
            html += '<div class="pl-dept-card">'
                + '<div class="pl-dept-name">' + esc(name) + '</div>'
                + '<div class="pl-dept-stats">'
                + '<div class="pl-dept-stat"><span class="pl-dept-stat-label">Deals</span><span class="pl-dept-stat-value">' + d.count + '</span></div>'
                + '<div class="pl-dept-stat"><span class="pl-dept-stat-label">Value</span><span class="pl-dept-stat-value">' + fmtCurrencyK(d.amount) + '</span></div>'
                + '<div class="pl-dept-stat"><span class="pl-dept-stat-label">Open</span><span class="pl-dept-stat-value">' + fmtCurrencyK(d.open) + '</span></div>'
                + '<div class="pl-dept-stat"><span class="pl-dept-stat-label">Won</span><span class="pl-dept-stat-value" style="color:var(--success)">' + fmtCurrencyK(d.won) + '</span></div>'
                + '</div></div>';
        });
        grid.innerHTML = html;

        // Toggle handler
        var toggle = document.getElementById('pl-dept-toggle');
        var header = document.querySelector('.pl-dept-header');
        if (toggle && header && !toggle._wired) {
            toggle._wired = true;
            header.addEventListener('click', function () {
                toggle.classList.toggle('collapsed');
                grid.classList.toggle('collapsed');
            });
        }
    }

    // ================================================================
    // Filter Count
    // ================================================================
    function renderFilterCount() {
        var el = document.getElementById('pl-filter-count');
        if (el) el.textContent = 'Showing ' + FILTERED.length + ' of ' + DEALS.length + ' deals';
    }

    // ================================================================
    // TABLE VIEW
    // ================================================================
    function renderTable() {
        var tbody = document.getElementById('pl-deals-body');
        if (!tbody) return;

        if (!FILTERED.length) {
            tbody.innerHTML = '<tr><td colspan="9" class="pl-empty">No deals match the current filters</td></tr>';
            return;
        }

        var html = '';
        FILTERED.forEach(function (d) {
            var cssClass = STAGE_CSS[d.stage] || 'qualified';
            var dealUrl = 'https://' + HUB_DOMAIN + '/contacts/' + HUB_ID + '/record/0-3/' + d.id;
            html += '<tr>'
                + '<td class="pl-deal-name"><a href="' + dealUrl + '" target="_blank" rel="noopener">' + esc(d.name) + '</a></td>'
                + '<td><span class="pl-deal-stage pl-stage-' + cssClass + '">' + esc(d.stage) + '</span></td>'
                + '<td>' + fmtDateShort(d.created) + '</td>'
                + '<td>' + esc(d.product || '—') + '</td>'
                + '<td>' + esc(d.source || '—') + '</td>'
                + '<td class="pl-deal-amt">' + fmtCurrency(d.amount) + '</td>'
                + '<td>' + esc(d.owner) + '</td>'
                + '<td class="pl-deal-muted">' + esc(d.lostReason || '—') + '</td>'
                + '<td class="pl-deal-muted">' + esc(d.wonReason || '—') + '</td>'
                + '</tr>';
        });
        tbody.innerHTML = html;

        var footer = document.getElementById('pl-table-footer');
        if (footer) {
            var totalAmt = FILTERED.reduce(function (s, d) { return s + d.amount; }, 0);
            footer.innerHTML = '<span>' + FILTERED.length + ' deals</span>'
                + '<span>Total: <strong>' + fmtCurrencyK(totalAmt) + '</strong></span>';
        }
    }

    function esc(s) {
        if (!s) return '';
        var d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    }

    // ================================================================
    // REPORT VIEW
    // ================================================================
    function renderReport() {
        renderFunnel();
        renderSourceBreakdown();
        renderProductBreakdown();
        renderOwnerBreakdown();
        renderMonthlyChart();
        renderWinLoss();
    }

    function renderFunnel() {
        var el = document.getElementById('pl-rpt-funnel');
        if (!el) return;

        var stageCounts = {};
        FILTERED.forEach(function (d) {
            stageCounts[d.stage] = (stageCounts[d.stage] || 0) + 1;
        });

        var maxCount = 0;
        STAGE_ORDER.forEach(function (s) {
            if ((stageCounts[s] || 0) > maxCount) maxCount = stageCounts[s];
        });
        if (maxCount === 0) maxCount = 1;

        var total = FILTERED.length || 1;
        var html = '<div class="pl-funnel-head">'
            + '<div>Stage</div><div>Deals</div><div style="text-align:center">Count</div>'
            + '<div style="text-align:center">% Share</div></div>';

        STAGE_ORDER.forEach(function (stage) {
            var count = stageCounts[stage] || 0;
            if (count === 0) return;
            var barPct = Math.max(2, (count / maxCount) * 100);
            var sharePct = (count / total * 100).toFixed(1);
            html += '<div class="pl-funnel-row">'
                + '<div class="pl-funnel-stage">' + stage + '</div>'
                + '<div class="pl-funnel-bar-wrap">'
                + '<div class="pl-funnel-bar-track">'
                + '<div class="pl-funnel-bar-fill" style="width:' + barPct.toFixed(1) + '%;background:' + (STAGE_COLOURS[stage] || 'var(--accent)') + '">'
                + '</div></div>'
                + '<span class="pl-funnel-bar-label">' + count + '</span></div>'
                + '<div class="pl-funnel-pct">' + count + '</div>'
                + '<div class="pl-funnel-pct">' + sharePct + '%</div>'
                + '</div>';
        });

        el.innerHTML = html;
    }

    function renderBreakdownTable(elId, groups, labelKey) {
        var el = document.getElementById(elId);
        if (!el) return;

        var sorted = Object.keys(groups).map(function (k) {
            return { label: k, count: groups[k].count, amount: groups[k].amount };
        }).sort(function (a, b) { return b.amount - a.amount; });

        if (!sorted.length) { el.innerHTML = '<div class="pl-empty">No data</div>'; return; }

        var maxAmt = sorted[0].amount || 1;
        var html = '<table class="pl-breakdown-table"><thead><tr>'
            + '<th>' + (labelKey || 'Name') + '</th><th class="num">Deals</th>'
            + '<th class="num">Value</th><th>Distribution</th>'
            + '</tr></thead><tbody>';

        sorted.forEach(function (row) {
            var barPct = Math.max(2, (row.amount / maxAmt) * 100);
            html += '<tr>'
                + '<td style="font-weight:600">' + esc(row.label || 'Unknown') + '</td>'
                + '<td class="num">' + row.count + '</td>'
                + '<td class="num" style="font-weight:600">' + fmtCurrencyK(row.amount) + '</td>'
                + '<td><div class="pl-breakdown-bar-wrap">'
                + '<div class="pl-breakdown-bar" style="width:' + barPct.toFixed(1) + '%"></div>'
                + '</div></td></tr>';
        });

        html += '</tbody></table>';
        el.innerHTML = html;
    }

    function renderSourceBreakdown() {
        var groups = {};
        FILTERED.forEach(function (d) {
            var key = d.source || 'Unknown';
            if (!groups[key]) groups[key] = { count: 0, amount: 0 };
            groups[key].count++;
            groups[key].amount += d.amount;
        });
        renderBreakdownTable('pl-rpt-source', groups, 'Source');
    }

    function renderProductBreakdown() {
        var groups = {};
        FILTERED.forEach(function (d) {
            var prods = d.product ? d.product.split(';') : ['Unknown'];
            prods.forEach(function (p) {
                p = p.trim() || 'Unknown';
                if (!groups[p]) groups[p] = { count: 0, amount: 0 };
                groups[p].count++;
                groups[p].amount += d.amount;
            });
        });
        renderBreakdownTable('pl-rpt-product', groups, 'Product');
    }

    function renderOwnerBreakdown() {
        var groups = {};
        FILTERED.forEach(function (d) {
            var key = d.owner || 'Unassigned';
            if (!groups[key]) groups[key] = { count: 0, amount: 0 };
            groups[key].count++;
            groups[key].amount += d.amount;
        });
        renderBreakdownTable('pl-rpt-owner', groups, 'Owner');
    }

    function renderMonthlyChart() {
        var el = document.getElementById('pl-rpt-monthly');
        if (!el) return;

        var monthly = {};
        FILTERED.forEach(function (d) {
            var m = d.created ? d.created.slice(0, 7) : null;
            if (m) monthly[m] = (monthly[m] || 0) + 1;
        });

        var months = Object.keys(monthly).sort().slice(-12);
        if (!months.length) { el.innerHTML = '<div class="pl-empty">No data</div>'; return; }
        var max = 0;
        months.forEach(function (m) { if (monthly[m] > max) max = monthly[m]; });
        if (!max) max = 1;

        var html = '<div style="display:flex;align-items:flex-end;gap:4px;height:160px;padding-top:20px">';
        months.forEach(function (m) {
            var pct = Math.max(2, Math.round(monthly[m] / max * 100));
            var parts = m.split('-');
            var label = MONTH_SHORT[parseInt(parts[1], 10) - 1] + ' ' + parts[0].slice(2);
            html += '<div style="flex:1;display:flex;flex-direction:column;align-items:center">'
                + '<div style="font-size:10px;color:var(--text-muted);margin-bottom:2px">' + monthly[m] + '</div>'
                + '<div style="width:100%;height:' + pct + '%;background:var(--accent);border-radius:3px 3px 0 0;min-height:2px"></div>'
                + '<div style="font-size:9px;color:var(--text-muted);margin-top:4px">' + label + '</div>'
                + '</div>';
        });
        html += '</div>';
        el.innerHTML = html;
    }

    function renderWinLoss() {
        var el = document.getElementById('pl-rpt-winloss');
        if (!el) return;

        var won = 0, lost = 0, open = 0;
        FILTERED.forEach(function (d) {
            if (d.isWon) won++;
            else if (d.isLost) lost++;
            else open++;
        });

        var closed = won + lost;
        var winRate = closed > 0 ? (won / closed * 100).toFixed(1) : '0';
        var lossRate = closed > 0 ? (lost / closed * 100).toFixed(1) : '0';
        var total = won + lost + open || 1;
        var wonPct = (won / total * 100).toFixed(1);
        var lostPct = (lost / total * 100).toFixed(1);
        var openPct = (open / total * 100).toFixed(1);

        var html = '<div class="pl-winloss-grid">'
            + '<div class="pl-winloss-stat">'
            + '<div class="pl-winloss-value" style="color:var(--success)">' + winRate + '%</div>'
            + '<div class="pl-winloss-label">Win Rate (' + won + ' won)</div></div>'
            + '<div class="pl-winloss-stat">'
            + '<div class="pl-winloss-value" style="color:var(--danger)">' + lossRate + '%</div>'
            + '<div class="pl-winloss-label">Loss Rate (' + lost + ' lost)</div></div>'
            + '</div>'
            + '<div class="pl-winloss-bar">'
            + '<div class="pl-winloss-bar-won" style="width:' + wonPct + '%"><span>' + won + '</span></div>'
            + '<div class="pl-winloss-bar-open" style="width:' + openPct + '%"><span>' + open + '</span></div>'
            + '<div class="pl-winloss-bar-lost" style="width:' + lostPct + '%"><span>' + lost + '</span></div>'
            + '</div>'
            + '<div style="display:flex;justify-content:space-between;margin-top:6px;font-size:10px;color:var(--text-muted);font-weight:600">'
            + '<span style="color:var(--success)">Won</span>'
            + '<span style="color:var(--accent)">Open</span>'
            + '<span style="color:var(--danger)">Lost</span></div>';

        el.innerHTML = html;
    }

    // ================================================================
    // GANTT VIEW
    // ================================================================
    function renderGantt() {
        var el = document.getElementById('pl-gantt-chart');
        if (!el) return;

        var openDeals = FILTERED.filter(function (d) { return !d.isWon && !d.isLost; });
        if (!openDeals.length) { el.innerHTML = '<div class="pl-empty">No open deals to display</div>'; return; }

        // Sort by create date
        openDeals.sort(function (a, b) { return new Date(a.created) - new Date(b.created); });

        // Calculate time range
        var now = new Date();
        var minDate = new Date(openDeals[0].created);
        var maxDate = new Date(now);
        // Extend 30 days into future
        maxDate.setDate(maxDate.getDate() + 30);

        var totalDays = daysBetween(minDate, maxDate) || 1;

        // Generate month headers
        var headers = [];
        var cur = new Date(minDate.getFullYear(), minDate.getMonth(), 1);
        while (cur <= maxDate) {
            headers.push({ label: MONTH_SHORT[cur.getMonth()] + ' ' + String(cur.getFullYear()).slice(2), date: new Date(cur) });
            cur.setMonth(cur.getMonth() + 1);
        }

        var html = '<div class="pl-gantt-header">'
            + '<div class="pl-gantt-header-cell" style="min-width:180px;text-align:left">Deal</div>';
        headers.forEach(function (h) {
            html += '<div class="pl-gantt-header-cell">' + h.label + '</div>';
        });
        html += '</div>';

        // Today marker position
        var todayPct = (daysBetween(minDate, now) / totalDays * 100);

        openDeals.forEach(function (d) {
            var start = new Date(d.created);
            var end = d.closed ? new Date(d.closed) : now;
            var leftPct = (daysBetween(minDate, start) / totalDays * 100);
            var widthPct = Math.max(1, (daysBetween(start, end) / totalDays * 100));
            var colour = STAGE_COLOURS[d.stage] || '#3CB4AD';

            html += '<div class="pl-gantt-row">'
                + '<div class="pl-gantt-label" title="' + esc(d.name) + '">' + esc(d.name) + '</div>'
                + '<div class="pl-gantt-track">'
                + '<div class="pl-gantt-bar" style="left:' + leftPct.toFixed(1) + '%;width:' + widthPct.toFixed(1) + '%;background:' + colour + '"'
                + ' title="' + esc(d.name) + ' — ' + esc(d.stage) + ' — ' + fmtCurrency(d.amount) + '">'
                + esc(d.stage) + '</div>'
                + '<div class="pl-gantt-today" style="left:' + todayPct.toFixed(1) + '%"></div>'
                + '</div></div>';
        });

        el.innerHTML = html;
    }

    // ================================================================
    // Populate Filter Dropdowns
    // ================================================================
    function populateFilters() {
        var owners = {}, products = {}, sources = {}, stages = {};
        DEALS.forEach(function (d) {
            if (d.owner) owners[d.owner] = true;
            if (d.product) d.product.split(';').forEach(function (p) { products[p.trim()] = true; });
            if (d.source) sources[d.source] = true;
            if (d.stage) stages[d.stage] = true;
        });

        fillSelect('pl-filter-owner', 'All Owners', Object.keys(owners).sort());
        fillSelect('pl-filter-product', 'All Products', Object.keys(products).sort());
        fillSelect('pl-filter-source', 'All Sources', Object.keys(sources).sort());
        fillSelect('pl-filter-stage', 'All Stages', STAGE_ORDER.filter(function (s) { return stages[s]; }));
    }

    function fillSelect(id, placeholder, options) {
        var sel = document.getElementById(id);
        if (!sel) return;
        sel.innerHTML = '<option value="">' + placeholder + '</option>';
        options.forEach(function (o) {
            sel.innerHTML += '<option value="' + esc(o) + '">' + esc(o) + '</option>';
        });
    }

    // ================================================================
    // Event Wiring
    // ================================================================
    function wireEvents() {
        // View tabs
        var section = document.getElementById('pipeline');
        if (!section) return;

        section.addEventListener('click', function (e) {
            // View tab click
            var tab = e.target.closest('.pl-view-tab');
            if (tab) {
                section.querySelectorAll('.pl-view-tab').forEach(function (t) {
                    t.classList.remove('active'); t.setAttribute('aria-selected', 'false');
                });
                tab.classList.add('active'); tab.setAttribute('aria-selected', 'true');
                ACTIVE_VIEW = tab.getAttribute('data-view');
                section.querySelectorAll('.pl-view-panel').forEach(function (p) { p.classList.remove('active'); });
                var panel = document.getElementById('pl-view-' + ACTIVE_VIEW);
                if (panel) panel.classList.add('active');
                renderActiveView();
                return;
            }

            // Period pill click
            var pill = e.target.closest('.pl-period-pill');
            if (pill) {
                section.querySelectorAll('.pl-period-pill').forEach(function (p) { p.classList.remove('active'); });
                pill.classList.add('active');
                ACTIVE_PERIOD = pill.getAttribute('data-period');
                applyFilters();
                return;
            }

            // Table sort
            var th = e.target.closest('.pl-deals-table thead th[data-sort]');
            if (th) {
                var key = th.getAttribute('data-sort');
                if (SORT_KEY === key) SORT_DIR = SORT_DIR === 'asc' ? 'desc' : 'asc';
                else { SORT_KEY = key; SORT_DIR = key === 'amount' ? 'desc' : 'asc'; }
                // Update sort indicators
                section.querySelectorAll('.pl-deals-table thead th').forEach(function (h) {
                    h.classList.remove('sorted-asc', 'sorted-desc');
                });
                th.classList.add('sorted-' + SORT_DIR);
                sortDeals();
                renderTable();
            }
        });

        // Filter selects
        ['pl-filter-owner', 'pl-filter-product', 'pl-filter-source', 'pl-filter-stage'].forEach(function (id) {
            var sel = document.getElementById(id);
            if (sel) sel.addEventListener('change', applyFilters);
        });
    }

    // ================================================================
    // Render Active View
    // ================================================================
    function renderActiveView() {
        if (ACTIVE_VIEW === 'table') renderTable();
        else if (ACTIVE_VIEW === 'report' && window.renderPipelineReports) window.renderPipelineReports(FILTERED, DEALS, ACTIVE_PERIOD);
        else if (ACTIVE_VIEW === 'gantt') renderGantt();
        else if (ACTIVE_VIEW === 'export' && window.renderPipelineExport) window.renderPipelineExport(FILTERED, DEALS, ACTIVE_PERIOD);
    }

    function renderAll() {
        renderSummary();
        renderDeptBreakdown();
        renderFilterCount();
        renderActiveView();
    }

    // ================================================================
    // Data Loading — live API with static fallback
    // ================================================================
    function loadDeals(callback) {
        // Try live API first (Supabase-cached HubSpot data)
        var xhr = new XMLHttpRequest();
        xhr.open('GET', '/api/deals', true);
        xhr.timeout = 8000;
        xhr.onload = function () {
            if (xhr.status === 200) {
                try {
                    var data = JSON.parse(xhr.responseText);
                    var meta = data.meta || {};
                    updateSyncBadge(meta.syncedAt, meta.source);
                    callback(data.deals || []);
                    return;
                } catch (e) { /* fall through */ }
            }
            loadStaticFallback(callback);
        };
        xhr.onerror = function () { loadStaticFallback(callback); };
        xhr.ontimeout = function () { loadStaticFallback(callback); };
        xhr.send();
    }

    function loadStaticFallback(callback) {
        var xhr = new XMLHttpRequest();
        xhr.open('GET', 'data/hubspot-deals.json?t=' + Date.now(), true);
        xhr.onload = function () {
            if (xhr.status === 200) {
                try {
                    var data = JSON.parse(xhr.responseText);
                    updateSyncBadge(data.meta && data.meta.syncedAt, 'static');
                    callback(data.deals || []);
                    return;
                } catch (e) { /* empty */ }
            }
            callback([]);
        };
        xhr.onerror = function () { callback([]); };
        xhr.send();
    }

    function updateSyncBadge(syncedAt, source) {
        var sub = document.querySelector('.section-subtitle');
        if (!sub) return;
        var ago = '';
        if (syncedAt) {
            var diff = Math.round((Date.now() - new Date(syncedAt).getTime()) / 60000);
            if (diff < 1) ago = 'just now';
            else if (diff < 60) ago = diff + ' min ago';
            else ago = Math.round(diff / 60) + 'h ago';
        }
        var label = source === 'hubspot' ? 'Live' : source === 'cache' ? 'Cached' : 'Static';
        var dot = source === 'hubspot' ? '#22c55e' : source === 'cache' ? '#3CB4AD' : '#f59e0b';
        sub.innerHTML = 'HubSpot deal pipeline — '
            + '<span style="display:inline-flex;align-items:center;gap:4px">'
            + '<span style="width:8px;height:8px;border-radius:50%;background:' + dot + ';display:inline-block"></span>'
            + label + (ago ? ' · synced ' + ago : '')
            + '</span>';
    }

    // ================================================================
    // Master Render
    // ================================================================
    window.renderPipeline = function () {
        loadDeals(function (deals) {
            DEALS = deals;
            FILTERED = filterByPeriod(DEALS, ACTIVE_PERIOD);
            populateFilters();
            sortDeals();
            renderAll();
            wireEvents();
        });
    };
})();
