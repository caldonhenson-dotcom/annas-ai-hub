/* ============================================================
   Filters — period buttons, KPI updates, chart refresh
   ============================================================ */
// ----------------------------------------------------------------
// Main filter application
// ----------------------------------------------------------------
window.applyFilter = function(period) {
    window.currentPeriod = period;
    var range = getDateRange(period);
    var showYoY = (period === 'ytd' || period === 'all' || period === 'last_year');

    // Update button states
    document.querySelectorAll('.filter-btn').forEach(function(btn) {
        btn.classList.toggle('active', btn.getAttribute('data-period') === period);
    });
    var label = document.getElementById('filter-period-label');
    if (label) label.textContent = PERIOD_LABELS[period] || '';

    // ---- Compute filtered values ----
    var leads = sumDaily(TS.leads_by_day, range);
    var contacts = sumDaily(TS.contacts_created_by_day, range);
    var dealsWon = sumDaily(TS.deals_won_by_day, range);
    var dealsLost = sumDaily(TS.deals_lost_by_day, range);
    var dealsCreated = sumDaily(TS.deals_created_by_day, range);
    var revenue = sumDaily(TS.deals_won_value_by_day, range);
    var activities = sumActivitiesDaily(TS.activities_by_type_by_day, range);
    var mqls = sumDaily(TS.mqls_by_day, range);
    var sqls = sumDaily(TS.sqls_by_day, range);
    var actBreakdown = getActivityBreakdown(TS.activities_by_type_by_day, range);
    var avgDeal = dealsWon > 0 ? revenue / dealsWon : 0;
    var winRate = (dealsWon + dealsLost) > 0 ? (dealsWon / (dealsWon + dealsLost) * 100) : 0;

    // ---- Update KPI cards ----
    // Find stat-card elements and update by matching title text
    var cards = document.querySelectorAll('.stat-card');
    cards.forEach(function(card) {
        var titleEl = card.querySelector('div[style*="text-transform:uppercase"]');
        if (!titleEl) return;
        var title = titleEl.textContent.trim().toLowerCase();
        var valueEl = card.querySelector('[data-role="stat-value"]');
        if (!valueEl) return;

        switch(title) {
            case 'total leads':
                valueEl.innerHTML = fmtNum(leads) + (showYoY ? yoyBadge('leads') : '');
                break;
            case 'total contacts':
                valueEl.innerHTML = fmtNum(contacts) + (showYoY ? yoyBadge('contacts_created') : '');
                break;
            case 'total activities':
                valueEl.innerHTML = fmtNum(activities) + (showYoY ? yoyBadge('activities') : '');
                break;
            case 'mql count':
                valueEl.innerHTML = fmtNum(mqls) + (showYoY ? yoyBadge('mqls') : '');
                break;
            case 'sql count':
                valueEl.innerHTML = fmtNum(sqls);
                break;
            case 'win rate':
                valueEl.innerHTML = winRate.toFixed(1) + '%';
                break;
            case 'avg deal size':
                valueEl.innerHTML = fmtCurrency(avgDeal) + (showYoY ? yoyBadge('avg_deal_size') : '');
                break;
            case 'pipeline value':
            case 'total pipeline':
                valueEl.innerHTML = fmtCurrency(revenue) + (showYoY ? yoyBadge('revenue_won') : '');
                break;
            case 'open deals':
                valueEl.innerHTML = fmtNum(dealsCreated) + (showYoY ? yoyBadge('deals_won') : '');
                break;
            case 'calls':
                valueEl.innerHTML = fmtNum(actBreakdown.calls);
                break;
            case 'emails':
                valueEl.innerHTML = fmtNum(actBreakdown.emails);
                break;
            case 'meetings':
                valueEl.innerHTML = fmtNum(actBreakdown.meetings);
                break;
            case 'tasks':
                valueEl.innerHTML = fmtNum(actBreakdown.tasks);
                break;
            case 'notes':
                valueEl.innerHTML = fmtNum(actBreakdown.notes);
                break;
        }
    });

    // ---- Update dynamic chart containers ----
    // Leads by source (filtered monthly)
    var leadSrcMonthly = {};
    if (TS.leads_by_source_by_month) {
        for (var month in TS.leads_by_source_by_month) {
            if (range === null || (month + '-01' >= range.start && month + '-01' <= range.end)
                || (month + '-28' >= range.start && month + '-01' <= range.end)) {
                var srcs = TS.leads_by_source_by_month[month];
                for (var src in srcs) {
                    leadSrcMonthly[src] = (leadSrcMonthly[src] || 0) + srcs[src];
                }
            }
        }
    }
    renderMiniBar('dynamic-leads-by-source', leadSrcMonthly);

    // Leads over time bar chart
    var leadsMonthly = filterDailyToMonthly(TS.leads_by_day, range);
    renderMonthlyBarChart('dynamic-leads-barchart', leadsMonthly, '#3CB4AD', false);

    // Activity trend sparkline
    var actDaily = {};
    if (TS.activities_by_type_by_day) {
        for (var day in TS.activities_by_type_by_day) {
            if (range === null || (day >= range.start && day <= range.end)) {
                var c = TS.activities_by_type_by_day[day];
                var mk = day.substring(0, 7);
                var total = 0;
                for (var t in c) total += c[t];
                actDaily[mk] = (actDaily[mk] || 0) + total;
            }
        }
    }
    renderMonthlyBarChart('dynamic-activity-barchart', actDaily, '#a78bfa', false);

    // Activity breakdown bars
    renderMiniBar('dynamic-activity-breakdown', actBreakdown);

    // Revenue by month sparkline
    var revMonthly = {};
    if (TS.deals_won_value_by_day) {
        for (var day in TS.deals_won_value_by_day) {
            if (range === null || (day >= range.start && day <= range.end)) {
                var mk = day.substring(0, 7);
                revMonthly[mk] = (revMonthly[mk] || 0) + TS.deals_won_value_by_day[day];
            }
        }
    }
    renderMonthlyBarChart('dynamic-revenue-barchart', revMonthly, '#34d399', true);

    // Deals created bar chart
    var dealsMonthly = filterDailyToMonthly(TS.deals_created_by_day, range);
    renderMonthlyBarChart('dynamic-deals-barchart', dealsMonthly, '#38bdf8', false);
};

// ---- Initialize on page load ----
document.addEventListener('DOMContentLoaded', function() {
    applyFilter('ytd');
});
})();
