/* ============================================================
   Chart Router — routes queries to visual card renderers
   ============================================================ */
(function () {
    'use strict';

    var MONTH_SHORT = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

    /** Convert daily series to monthly totals (last 6 months). */
    function toMonthly(daily) {
        var buckets = {};
        for (var d in daily) {
            var mk = d.substring(0, 7);
            buckets[mk] = (buckets[mk] || 0) + daily[d];
        }
        var sorted = Object.keys(buckets).sort();
        if (sorted.length > 6) sorted = sorted.slice(sorted.length - 6);
        var labels = sorted.map(function (k) { return MONTH_SHORT[parseInt(k.split('-')[1], 10) - 1]; });
        var data = sorted.map(function (k) { return buckets[k]; });
        return { labels: labels, data: data };
    }

    /** Sum all values in a daily series. */
    function sumAll(daily) {
        var total = 0;
        for (var k in daily) total += daily[k];
        return total;
    }

    // ------------------------------------------------------------------
    // Quick Question Templates
    // ------------------------------------------------------------------
    var TEMPLATES = {

        'pipeline': function () {
            var kpis = (window.STATIC && window.STATIC.EXEC_KPIS) || [];
            var rev = toMonthly(window.TS.deals_won_value_by_day || {});
            return [
                { type: 'kpi', kpis: kpis.slice(0, 4) },
                { type: 'chart', title: 'Revenue by Month', icon: '&#128176;',
                    type_chart: 'bar', labels: rev.labels, currency: true,
                    datasets: [{ label: 'Won Revenue', data: rev.data, color: '#3CB4AD' }] },
                { type: 'text', title: 'Pipeline Summary',
                    text: buildPipelineSummary() }
            ];
        },

        'revenue by month': function () {
            var rev = toMonthly(window.TS.deals_won_value_by_day || {});
            var total = sumAll(window.TS.deals_won_value_by_day || {});
            return [
                { type: 'kpi', kpis: [
                    { label: 'Total Revenue', value: '\u00a3' + fmtNum(total), color: '#3CB4AD' },
                    { label: 'Monthly Avg', value: '\u00a3' + fmtNum(Math.round(total / Math.max(rev.labels.length, 1))), color: '#334FB4' },
                    { label: 'Best Month', value: '\u00a3' + fmtNum(Math.max.apply(null, rev.data.length ? rev.data : [0])), color: '#34d399' }
                ] },
                { type: 'chart', title: 'Revenue by Month', icon: '&#128176;',
                    subtitle: 'Last 6 months', type_chart: 'bar', labels: rev.labels, currency: true,
                    datasets: [{ label: 'Won Revenue', data: rev.data, color: '#3CB4AD' }] }
            ];
        },

        'deal flow': function () {
            var won = toMonthly(window.TS.deals_won_by_day || {});
            var lost = toMonthly(window.TS.deals_lost_by_day || {});
            var created = toMonthly(window.TS.deals_created_by_day || {});
            return [
                { type: 'kpi', kpis: [
                    { label: 'Deals Created', value: fmtNum(sumAll(window.TS.deals_created_by_day || {})), color: '#3CB4AD' },
                    { label: 'Deals Won', value: fmtNum(sumAll(window.TS.deals_won_by_day || {})), color: '#34d399' },
                    { label: 'Deals Lost', value: fmtNum(sumAll(window.TS.deals_lost_by_day || {})), color: '#ef4444' }
                ] },
                { type: 'chart', title: 'Deal Flow Over Time', icon: '&#128200;',
                    subtitle: 'Created vs Won vs Lost', type_chart: 'line', labels: created.labels,
                    datasets: [
                        { label: 'Created', data: created.data, color: '#334FB4' },
                        { label: 'Won', data: won.data, color: '#34d399' },
                        { label: 'Lost', data: lost.data, color: '#ef4444' }
                    ] }
            ];
        },

        'win rate': function () {
            var won = sumAll(window.TS.deals_won_by_day || {});
            var lost = sumAll(window.TS.deals_lost_by_day || {});
            var total = won + lost;
            var rate = total > 0 ? (won / total * 100).toFixed(1) : '0.0';
            return [
                { type: 'kpi', kpis: [
                    { label: 'Win Rate', value: rate + '%', color: '#34d399' },
                    { label: 'Won', value: String(won), color: '#22c55e' },
                    { label: 'Lost', value: String(lost), color: '#ef4444' },
                    { label: 'Total Decided', value: String(total), color: '#334FB4' }
                ] },
                { type: 'chart', title: 'Win / Loss Ratio', icon: '&#127919;',
                    type_chart: 'doughnut', labels: ['Won', 'Lost'],
                    datasets: [{ label: 'Deals', data: [won, lost], color: '#34d399' }] }
            ];
        },

        'activity breakdown': function () {
            var bd = {};
            var series = window.TS.activities_by_type_by_day || {};
            for (var day in series) {
                var types = series[day];
                for (var t in types) bd[t] = (bd[t] || 0) + types[t];
            }
            var sorted = Object.entries(bd).sort(function (a, b) { return b[1] - a[1]; });
            return [
                { type: 'kpi', kpis: [
                    { label: 'Total Activities', value: fmtNum(sumAll(buildActivityDaily())), color: '#f472b6' }
                ] },
                { type: 'chart', title: 'Activity Breakdown', icon: '&#128203;',
                    type_chart: 'bar', labels: sorted.map(function (s) { return s[0]; }),
                    datasets: [{ label: 'Count', data: sorted.map(function (s) { return s[1]; }), color: '#f472b6' }] }
            ];
        },

        'lead sources': function () {
            var srcData = {};
            var series = window.TS.leads_by_source_by_month || {};
            for (var month in series) {
                var srcs = series[month];
                for (var s in srcs) srcData[s] = (srcData[s] || 0) + srcs[s];
            }
            var sorted = Object.entries(srcData).sort(function (a, b) { return b[1] - a[1]; }).slice(0, 8);
            return [
                { type: 'kpi', kpis: [
                    { label: 'Total Leads', value: fmtNum(sumAll(window.TS.leads_by_day || {})), color: '#3b82f6' },
                    { label: 'Top Source', value: sorted.length ? sorted[0][0] : 'N/A', color: '#334FB4' }
                ] },
                { type: 'chart', title: 'Lead Sources', icon: '&#128161;',
                    type_chart: 'bar', labels: sorted.map(function (s) { return s[0]; }),
                    datasets: [{ label: 'Leads', data: sorted.map(function (s) { return s[1]; }), color: '#3b82f6' }] }
            ];
        }
    };

    /** Build a short pipeline summary from STATIC data. */
    function buildPipelineSummary() {
        var pillars = (window.STATIC && window.STATIC.EXEC_PILLARS) || [];
        var sales = pillars[0];
        if (!sales) return 'Pipeline data not available.';
        return sales.points.join('\n');
    }

    /** Sum activities_by_type_by_day into a flat daily total. */
    function buildActivityDaily() {
        var out = {};
        var series = window.TS.activities_by_type_by_day || {};
        for (var day in series) {
            var types = series[day]; var sum = 0;
            for (var t in types) sum += types[t];
            out[day] = sum;
        }
        return out;
    }

    // ------------------------------------------------------------------
    // LLM Response Parsing
    // ------------------------------------------------------------------

    /** Extract a ```json block from LLM text. */
    function extractJsonBlock(text) {
        var match = text.match(/```json\s*([\s\S]*?)```/);
        if (!match) return null;
        try { return JSON.parse(match[1]); } catch (e) { return null; }
    }

    /** Strip the json block from text, return the prose. */
    function stripJsonBlock(text) {
        return text.replace(/```json\s*[\s\S]*?```/g, '').trim();
    }

    // ------------------------------------------------------------------
    // Main Router
    // ------------------------------------------------------------------

    /** Route a query + answer to the right visualization. */
    function routeResponse(answer, query) {
        var q = (query || '').toLowerCase().trim();

        // 1. Check quick question templates
        var templateFn = matchTemplate(q);
        if (templateFn) {
            var cards = fixCardTypes(templateFn());
            window.ResponseCards.mixed(cards);
            return { rendered: true, type: 'template' };
        }

        // 2. Check for embedded JSON chart spec from LLM
        var spec = extractJsonBlock(answer || '');
        if (spec && spec.visualType) {
            var prose = stripJsonBlock(answer);
            renderFromSpec(spec, prose);
            return { rendered: true, type: 'llm-visual' };
        }

        // 3. Fallback: render as rich text card
        window.ResponseCards.clear();
        window.ResponseCards.text(answer || 'No response.', null);
        return { rendered: true, type: 'text' };
    }

    /** Match a query to a template (fuzzy). */
    function matchTemplate(q) {
        for (var key in TEMPLATES) {
            if (q === key || q.indexOf(key) >= 0) return TEMPLATES[key];
        }
        // Fuzzy matches
        if (q.indexOf('revenue') >= 0 || q.indexOf('monthly') >= 0) return TEMPLATES['revenue by month'];
        if (q.indexOf('deal') >= 0 && q.indexOf('flow') >= 0) return TEMPLATES['deal flow'];
        if (q.indexOf('win') >= 0 && q.indexOf('rate') >= 0) return TEMPLATES['win rate'];
        if (q.indexOf('activity') >= 0 || q.indexOf('activities') >= 0) return TEMPLATES['activity breakdown'];
        if (q.indexOf('lead') >= 0 && q.indexOf('source') >= 0) return TEMPLATES['lead sources'];
        return null;
    }

    /** Fix chart card types — template uses type_chart to avoid conflict with mixed type. */
    function fixCardTypes(cards) {
        return cards.map(function (c) {
            if (c.type_chart) {
                var chartType = c.type_chart;
                delete c.type_chart;
                return { type: 'chart', title: c.title, icon: c.icon, subtitle: c.subtitle,
                    chartType: chartType, labels: c.labels, datasets: c.datasets, currency: c.currency };
            }
            return c;
        });
    }

    /** Render from an LLM JSON spec. */
    function renderFromSpec(spec, prose) {
        window.ResponseCards.clear();
        if (spec.kpis) window.ResponseCards.kpi(spec.kpis);
        if (spec.chart) {
            window.ResponseCards.chart({
                title: spec.title || 'Chart', type: spec.chart.type || 'bar',
                labels: spec.chart.labels || [], datasets: spec.chart.datasets || [],
                currency: spec.chart.currency || false
            });
        }
        if (spec.table) window.ResponseCards.table(spec.table);
        if (spec.board) window.ResponseCards.board(spec.board);
        if (prose) window.ResponseCards.text(prose, null);
    }

    /** Check if a query matches a quick question (no LLM needed). */
    function isQuickQuestion(query) {
        return matchTemplate((query || '').toLowerCase().trim()) !== null;
    }

    // Expose
    window.ChartRouter = {
        route: routeResponse,
        isQuick: isQuickQuestion,
        extractJson: extractJsonBlock,
        stripJson: stripJsonBlock
    };

})();
