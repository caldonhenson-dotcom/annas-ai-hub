/* ============================================================
   Pipeline Reports — 10 advanced marketing/sales reports
   Depends on render-pipeline.js (shared helpers on window)
   ============================================================ */
(function () {
    'use strict';

    var STAGE_ORDER = [
        'Qualified Lead', 'Engaged', 'First Meeting Booked',
        'Second Meeting Booked', 'Proposal Shared',
        'Decision Maker Bought-In', 'Contract Sent',
        'Closed Won', 'Closed Lost', 'Disqualified'
    ];

    var STAGE_COLOURS = {
        'Qualified Lead': '#6b7280', 'Engaged': '#3CB4AD',
        'First Meeting Booked': '#3b82f6', 'Second Meeting Booked': '#3b82f6',
        'Proposal Shared': '#8b5cf6', 'Decision Maker Bought-In': '#f59e0b',
        'Contract Sent': '#10b981', 'Closed Won': '#22c55e',
        'Closed Lost': '#ef4444', 'Disqualified': '#6b7280'
    };

    var STAGE_CSS = {
        'Qualified Lead': 'qualified', 'Engaged': 'engaged',
        'First Meeting Booked': 'meeting', 'Second Meeting Booked': 'meeting',
        'Proposal Shared': 'proposal', 'Decision Maker Bought-In': 'decision',
        'Contract Sent': 'contract', 'Closed Won': 'won',
        'Closed Lost': 'lost', 'Disqualified': 'disqualified'
    };

    var MONTH_SHORT = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

    function fmtK(v) {
        if (v >= 1000000) return '£' + (v / 1000000).toFixed(2) + 'M';
        if (v >= 1000) return '£' + (v / 1000).toFixed(1) + 'K';
        return '£' + Number(v).toLocaleString('en-GB');
    }
    function esc(s) { var d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }
    function daysBetween(a, b) { return Math.round(Math.abs(new Date(b) - new Date(a)) / 86400000); }
    function initials(n) { return (n || '?').split(' ').map(function(w){return w[0]||'';}).join('').toUpperCase(); }

    // ── Build a breakdown table ──
    function breakdownHTML(rows, cols) {
        if (!rows.length) return '<div class="pl-empty">No data</div>';
        var maxVal = rows[0][cols[2].key] || 1;
        var html = '<table class="pl-breakdown-table"><thead><tr>';
        cols.forEach(function (c) { html += '<th' + (c.num ? ' class="num"' : '') + '>' + c.label + '</th>'; });
        html += '<th>Distribution</th></tr></thead><tbody>';
        rows.forEach(function (r) {
            var barPct = Math.max(2, (r[cols[2].key] / maxVal * 100));
            html += '<tr>';
            cols.forEach(function (c) {
                var val = c.fmt ? c.fmt(r[c.key]) : r[c.key];
                html += '<td' + (c.num ? ' class="num"' : '') + (c.bold ? ' style="font-weight:600"' : '') + '>' + val + '</td>';
            });
            html += '<td><div class="pl-breakdown-bar-wrap"><div class="pl-breakdown-bar" style="width:' + barPct.toFixed(1) + '%"></div></div></td></tr>';
        });
        html += '</tbody></table>';
        return html;
    }

    // ================================================================
    // Report 1: Pipeline Health
    // ================================================================
    function rptPipelineHealth(deals) {
        var open = deals.filter(function(d){return !d.isWon && !d.isLost;});
        var won = deals.filter(function(d){return d.isWon;});
        var lost = deals.filter(function(d){return d.isLost;});
        var openVal = open.reduce(function(s,d){return s+d.amount;},0);
        var wonVal = won.reduce(function(s,d){return s+d.amount;},0);
        var coverage = wonVal > 0 ? (openVal / wonVal).toFixed(1) : '∞';
        var winRate = (won.length + lost.length) > 0 ? (won.length / (won.length + lost.length) * 100).toFixed(1) : '0';
        var avgDealSize = deals.length > 0 ? deals.reduce(function(s,d){return s+d.amount;},0) / deals.length : 0;

        return '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:16px">'
            + metric('Coverage Ratio', coverage + 'x', 'Pipeline ÷ Won')
            + metric('Win Rate', winRate + '%', won.length + ' won / ' + (won.length+lost.length) + ' closed')
            + metric('Avg Deal Size', fmtK(avgDealSize), deals.length + ' total deals')
            + '</div>'
            + '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px">'
            + metric('Open Pipeline', fmtK(openVal), open.length + ' deals', 'var(--accent)')
            + metric('Closed Won', fmtK(wonVal), won.length + ' deals', 'var(--success)')
            + metric('Closed Lost', fmtK(lost.reduce(function(s,d){return s+d.amount;},0)), lost.length + ' deals', 'var(--danger)')
            + '</div>';
    }

    // ================================================================
    // Report 2: Stage Funnel
    // ================================================================
    function rptStageFunnel(deals) {
        var counts = {};
        deals.forEach(function(d){ counts[d.stage] = (counts[d.stage]||0) + 1; });
        var max = 0;
        STAGE_ORDER.forEach(function(s){ if ((counts[s]||0) > max) max = counts[s]; });
        if (!max) max = 1;
        var total = deals.length || 1;
        var html = '<div class="pl-funnel-head"><div>Stage</div><div>Deals</div><div style="text-align:center">Count</div><div style="text-align:center">% Share</div></div>';
        STAGE_ORDER.forEach(function(s){
            var c = counts[s] || 0; if (!c) return;
            var pct = Math.max(2, c/max*100);
            html += '<div class="pl-funnel-row"><div class="pl-funnel-stage">' + s + '</div>'
                + '<div class="pl-funnel-bar-wrap"><div class="pl-funnel-bar-track"><div class="pl-funnel-bar-fill" style="width:'+pct.toFixed(1)+'%;background:'+(STAGE_COLOURS[s]||'var(--accent)')+'"></div></div>'
                + '<span class="pl-funnel-bar-label">'+c+'</span></div>'
                + '<div class="pl-funnel-pct">'+c+'</div><div class="pl-funnel-pct">'+(c/total*100).toFixed(1)+'%</div></div>';
        });
        return html;
    }

    // ================================================================
    // Report 3: Source ROI
    // ================================================================
    function rptSourceROI(deals) {
        var groups = {};
        deals.forEach(function(d){
            var k = d.source || 'Unknown';
            if (!groups[k]) groups[k] = {name:k,count:0,amount:0,won:0,wonCount:0};
            groups[k].count++; groups[k].amount += d.amount;
            if (d.isWon) { groups[k].won += d.amount; groups[k].wonCount++; }
        });
        var rows = Object.values(groups).sort(function(a,b){return b.amount-a.amount;});
        return breakdownHTML(rows, [
            {key:'name',label:'Source',bold:true},
            {key:'count',label:'Deals',num:true},
            {key:'amount',label:'Value',num:true,fmt:fmtK},
            {key:'wonCount',label:'Won',num:true}
        ]);
    }

    // ================================================================
    // Report 4: Product Performance
    // ================================================================
    function rptProductPerf(deals) {
        var groups = {};
        deals.forEach(function(d){
            (d.product||'Unknown').split(';').forEach(function(p){
                p = p.trim()||'Unknown';
                if (!groups[p]) groups[p] = {name:p,count:0,amount:0,won:0,wonCount:0};
                groups[p].count++; groups[p].amount += d.amount;
                if (d.isWon) { groups[p].won += d.amount; groups[p].wonCount++; }
            });
        });
        var rows = Object.values(groups).sort(function(a,b){return b.amount-a.amount;});
        return breakdownHTML(rows, [
            {key:'name',label:'Product',bold:true},
            {key:'count',label:'Deals',num:true},
            {key:'amount',label:'Value',num:true,fmt:fmtK},
            {key:'wonCount',label:'Won',num:true}
        ]);
    }

    // ================================================================
    // Report 5: Rep Scorecard
    // ================================================================
    function rptRepScorecard(deals) {
        var reps = {};
        deals.forEach(function(d){
            var k = d.owner || 'Unassigned';
            if (!reps[k]) reps[k] = {name:k,count:0,amount:0,won:0,lost:0,wonCount:0,lostCount:0};
            reps[k].count++; reps[k].amount += d.amount;
            if (d.isWon) { reps[k].won += d.amount; reps[k].wonCount++; }
            if (d.isLost) { reps[k].lost += d.amount; reps[k].lostCount++; }
        });

        var sorted = Object.values(reps).sort(function(a,b){return b.amount-a.amount;});
        if (!sorted.length) return '<div class="pl-empty">No data</div>';

        var html = '<table class="pl-breakdown-table"><thead><tr>'
            + '<th>Rep</th><th class="num">Deals</th><th class="num">Value</th>'
            + '<th class="num">Won</th><th class="num">Lost</th><th class="num">Win Rate</th>'
            + '</tr></thead><tbody>';
        sorted.forEach(function(r){
            var closed = r.wonCount + r.lostCount;
            var rate = closed > 0 ? (r.wonCount/closed*100).toFixed(0) + '%' : '—';
            html += '<tr><td style="font-weight:600"><span class="pl-leader-avatar" style="display:inline-flex;width:22px;height:22px;font-size:9px;margin-right:6px;vertical-align:middle">'
                + initials(r.name) + '</span>' + esc(r.name) + '</td>'
                + '<td class="num">' + r.count + '</td><td class="num" style="font-weight:600">' + fmtK(r.amount) + '</td>'
                + '<td class="num" style="color:var(--success)">' + fmtK(r.won) + '</td>'
                + '<td class="num" style="color:var(--danger)">' + fmtK(r.lost) + '</td>'
                + '<td class="num" style="font-weight:700">' + rate + '</td></tr>';
        });
        html += '</tbody></table>';
        return html;
    }

    // ================================================================
    // Report 6: Deal Velocity (avg days per stage)
    // ================================================================
    function rptDealVelocity(deals) {
        var now = new Date();
        var stageAges = {};
        deals.forEach(function(d){
            if (d.isWon || d.isLost) return;
            var days = daysBetween(d.created, now);
            var s = d.stage;
            if (!stageAges[s]) stageAges[s] = {total:0,count:0};
            stageAges[s].total += days; stageAges[s].count++;
        });

        var rows = STAGE_ORDER.filter(function(s){return stageAges[s];}).map(function(s){
            var avg = (stageAges[s].total / stageAges[s].count).toFixed(0);
            return {stage:s,count:stageAges[s].count,avgDays:parseInt(avg),css:STAGE_CSS[s]||'qualified'};
        });

        if (!rows.length) return '<div class="pl-empty">No open deals</div>';
        var maxDays = Math.max.apply(null, rows.map(function(r){return r.avgDays;})) || 1;

        var html = '<table class="pl-breakdown-table"><thead><tr><th>Stage</th><th class="num">Deals</th><th class="num">Avg Days</th><th>Velocity</th></tr></thead><tbody>';
        rows.forEach(function(r){
            var pct = Math.max(2, r.avgDays/maxDays*100);
            var color = r.avgDays > 90 ? 'var(--danger)' : r.avgDays > 45 ? 'var(--warning)' : 'var(--success)';
            html += '<tr><td><span class="pl-deal-stage pl-stage-'+r.css+'">' + esc(r.stage) + '</span></td>'
                + '<td class="num">' + r.count + '</td>'
                + '<td class="num" style="font-weight:700;color:' + color + '">' + r.avgDays + 'd</td>'
                + '<td><div class="pl-breakdown-bar-wrap"><div class="pl-breakdown-bar" style="width:'+pct.toFixed(1)+'%;background:'+color+'"></div></div></td></tr>';
        });
        html += '</tbody></table>';
        return html;
    }

    // ================================================================
    // Report 7: Win/Loss Analysis
    // ================================================================
    function rptWinLoss(deals) {
        var won = deals.filter(function(d){return d.isWon;});
        var lost = deals.filter(function(d){return d.isLost;});
        var closed = won.length + lost.length;
        var winRate = closed > 0 ? (won.length/closed*100).toFixed(1) : '0';
        var wonVal = won.reduce(function(s,d){return s+d.amount;},0);
        var lostVal = lost.reduce(function(s,d){return s+d.amount;},0);

        // Lost reasons
        var reasons = {};
        lost.forEach(function(d){
            var r = d.lostReason || 'Not specified';
            reasons[r] = (reasons[r]||0) + 1;
        });
        var reasonRows = Object.keys(reasons).map(function(k){return {reason:k,count:reasons[k]};})
            .sort(function(a,b){return b.count-a.count;});

        var html = '<div class="pl-winloss-grid">'
            + '<div class="pl-winloss-stat"><div class="pl-winloss-value" style="color:var(--success)">' + winRate + '%</div><div class="pl-winloss-label">Win Rate (' + won.length + ')</div></div>'
            + '<div class="pl-winloss-stat"><div class="pl-winloss-value" style="color:var(--danger)">' + (100-parseFloat(winRate)).toFixed(1) + '%</div><div class="pl-winloss-label">Loss Rate (' + lost.length + ')</div></div></div>'
            + '<div class="pl-winloss-bar" style="margin:16px 0">'
            + '<div class="pl-winloss-bar-won" style="width:' + (closed>0?won.length/closed*100:50).toFixed(1) + '%"><span>' + fmtK(wonVal) + '</span></div>'
            + '<div class="pl-winloss-bar-lost" style="width:' + (closed>0?lost.length/closed*100:50).toFixed(1) + '%"><span>' + fmtK(lostVal) + '</span></div></div>';

        if (reasonRows.length) {
            html += '<div style="margin-top:12px;font-size:12px;font-weight:700;color:var(--text);margin-bottom:6px">Lost Reasons</div>';
            reasonRows.forEach(function(r){
                html += '<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--card-border);font-size:12px">'
                    + '<span style="color:var(--text)">' + esc(r.reason) + '</span>'
                    + '<span style="font-weight:600;color:var(--danger)">' + r.count + '</span></div>';
            });
        }
        return html;
    }

    // ================================================================
    // Report 8: Forecast
    // ================================================================
    function rptForecast(deals) {
        var open = deals.filter(function(d){return !d.isWon && !d.isLost;});
        var months = {};
        open.forEach(function(d){
            var m = d.closed ? d.closed.slice(0,7) : 'No close date';
            if (!months[m]) months[m] = {count:0,amount:0,weighted:0};
            months[m].count++; months[m].amount += d.amount; months[m].weighted += d.weighted;
        });

        var rows = Object.keys(months).sort().map(function(m){
            var label = m;
            if (m !== 'No close date') {
                var p = m.split('-');
                label = MONTH_SHORT[parseInt(p[1],10)-1] + ' ' + p[0];
            }
            return {month:label,count:months[m].count,amount:months[m].amount,weighted:months[m].weighted};
        });

        return breakdownHTML(rows, [
            {key:'month',label:'Close Month',bold:true},
            {key:'count',label:'Deals',num:true},
            {key:'amount',label:'Pipeline',num:true,fmt:fmtK},
            {key:'weighted',label:'Weighted',num:true,fmt:fmtK}
        ]);
    }

    // ================================================================
    // Report 9: Stale Deals
    // ================================================================
    function rptStaleDeals(deals) {
        var now = new Date();
        var stale = deals.filter(function(d){
            if (d.isWon || d.isLost) return false;
            var lastAct = d.lastActivity || d.lastContacted || d.created;
            return daysBetween(lastAct, now) > 30;
        }).map(function(d){
            var lastAct = d.lastActivity || d.lastContacted || d.created;
            return {name:d.name,stage:d.stage,amount:d.amount,owner:d.owner,days:daysBetween(lastAct,now),css:STAGE_CSS[d.stage]||'qualified'};
        }).sort(function(a,b){return b.days-a.days;});

        if (!stale.length) return '<div class="pl-empty" style="padding:24px">No stale deals — all deals have recent activity</div>';

        var html = '<table class="pl-breakdown-table"><thead><tr><th>Deal</th><th>Stage</th><th class="num">Value</th><th class="num">Days Stale</th><th>Owner</th></tr></thead><tbody>';
        stale.forEach(function(d){
            var color = d.days > 60 ? 'var(--danger)' : 'var(--warning)';
            html += '<tr><td style="font-weight:600;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + esc(d.name) + '</td>'
                + '<td><span class="pl-deal-stage pl-stage-' + d.css + '">' + esc(d.stage) + '</span></td>'
                + '<td class="num" style="font-weight:600">' + fmtK(d.amount) + '</td>'
                + '<td class="num" style="font-weight:700;color:' + color + '">' + d.days + 'd</td>'
                + '<td>' + esc(d.owner) + '</td></tr>';
        });
        html += '</tbody></table>';
        return html;
    }

    // ================================================================
    // Report 10: Monthly Trends (MoM + YoY)
    // ================================================================
    function rptMonthlyTrends(deals, allDeals) {
        var monthly = {};
        deals.forEach(function(d){
            var m = d.created ? d.created.slice(0,7) : null;
            if (!m) return;
            if (!monthly[m]) monthly[m] = {count:0,amount:0,won:0,lost:0};
            monthly[m].count++; monthly[m].amount += d.amount;
            if (d.isWon) monthly[m].won += d.amount;
            if (d.isLost) monthly[m].lost += d.amount;
        });

        var months = Object.keys(monthly).sort().slice(-12);
        if (!months.length) return '<div class="pl-empty">No data</div>';

        var html = '<table class="pl-breakdown-table"><thead><tr>'
            + '<th>Month</th><th class="num">Created</th><th class="num">Value</th>'
            + '<th class="num">Won</th><th class="num">Lost</th><th class="num">MoM</th>'
            + '</tr></thead><tbody>';

        var prevCount = null;
        months.forEach(function(m){
            var d = monthly[m];
            var parts = m.split('-');
            var label = MONTH_SHORT[parseInt(parts[1],10)-1] + ' ' + parts[0];
            var mom = prevCount !== null && prevCount > 0 ? ((d.count - prevCount)/prevCount*100).toFixed(0) : '—';
            var momCls = mom === '—' ? '' : parseInt(mom) > 0 ? 'color:var(--success)' : parseInt(mom) < 0 ? 'color:var(--danger)' : '';
            html += '<tr><td style="font-weight:600">' + label + '</td>'
                + '<td class="num">' + d.count + '</td>'
                + '<td class="num" style="font-weight:600">' + fmtK(d.amount) + '</td>'
                + '<td class="num" style="color:var(--success)">' + fmtK(d.won) + '</td>'
                + '<td class="num" style="color:var(--danger)">' + fmtK(d.lost) + '</td>'
                + '<td class="num" style="font-weight:600;' + momCls + '">' + (mom === '—' ? '—' : mom + '%') + '</td></tr>';
            prevCount = d.count;
        });
        html += '</tbody></table>';
        return html;
    }

    // ── Metric helper ──
    function metric(label, value, sub, color) {
        return '<div style="text-align:center;padding:12px;background:var(--surface2);border-radius:var(--radius)">'
            + '<div style="font-size:10px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.04em">' + label + '</div>'
            + '<div style="font-family:var(--font-display);font-size:24px;font-weight:400;color:' + (color||'var(--text)') + ';line-height:1.2">' + value + '</div>'
            + '<div style="font-size:10px;color:var(--text-muted);margin-top:2px">' + sub + '</div></div>';
    }

    // ================================================================
    // Master renderer
    // ================================================================
    var REPORTS = [
        { id: 'health', title: 'Pipeline Health', render: rptPipelineHealth, full: true },
        { id: 'funnel', title: 'Deal Stage Funnel', render: rptStageFunnel },
        { id: 'winloss', title: 'Win / Loss Analysis', render: rptWinLoss },
        { id: 'source', title: 'Source ROI', render: rptSourceROI },
        { id: 'product', title: 'Product Performance', render: rptProductPerf },
        { id: 'reps', title: 'Sales Rep Scorecard', render: rptRepScorecard, full: true },
        { id: 'velocity', title: 'Deal Velocity', render: rptDealVelocity },
        { id: 'forecast', title: 'Forecast', render: rptForecast },
        { id: 'stale', title: 'Stale Deals', render: rptStaleDeals, full: true },
        { id: 'trends', title: 'Monthly Trends', render: rptMonthlyTrends, full: true }
    ];

    window.renderPipelineReports = function (filtered, allDeals, period) {
        var el = document.getElementById('pl-reports-container');
        if (!el) return;

        var html = '<div class="pl-report-grid">';
        REPORTS.forEach(function (rpt) {
            var content = rpt.render(filtered, allDeals, period);
            html += '<div class="pl-card' + (rpt.full ? ' pl-report-full' : '') + '">'
                + '<div class="pl-card-header"><div class="pl-card-title">' + rpt.title + '</div></div>'
                + content + '</div>';
        });
        html += '</div>';
        el.innerHTML = html;
    };
})();
