/* ============================================================
   Static Data — structured data extracted from page HTML
   ============================================================ */
(function () {
    'use strict';

    window.STATIC = {

        // ── Executive Summary Pillars ──
        EXEC_KPIS: [
            { label: 'Pipeline',    value: '£793.7K', color: '#3CB4AD' },
            { label: 'Weighted',    value: '£355.9K', color: '#334FB4' },
            { label: 'Win Rate',    value: '26.3%',   color: '#34d399' },
            { label: 'Open Deals',  value: '59',      color: '#a78bfa' },
            { label: 'Avg Size',    value: '£15.7K',  color: '#f59e0b' },
            { label: 'Leads',       value: '46,231',  color: '#3b82f6' },
            { label: 'Activities',  value: '12,116',  color: '#f472b6' },
            { label: '30d Forecast', value: '£355.9K', color: '#f59e0b' }
        ],

        EXEC_PILLARS: [
            {
                title: 'Sales & Pipeline', icon: '&#9733;', color: '#3CB4AD',
                page: 'pipeline',
                points: [
                    '<strong>£793.7K</strong> total pipeline (59 open deals)',
                    '<strong>10</strong> deals won vs <strong>28</strong> lost &mdash; 26.3% win rate',
                    'Average sales cycle: <strong>104.9 days</strong>',
                    'Pipeline coverage: <strong>7.9x</strong> target'
                ]
            },
            {
                title: 'Leads & Conversion', icon: '&#10024;', color: '#334FB4',
                page: 'leads',
                points: [
                    '<strong>46,231</strong> total leads (1,693 new in last 30d)',
                    'Top source: <strong>OFFLINE</strong> (46,171 leads)',
                    '<strong>46,231</strong> contacts, <strong>18,193</strong> companies in CRM'
                ]
            },
            {
                title: 'M&A', icon: '&#128188;', color: '#a78bfa',
                page: 'monday-pipeline',
                points: [
                    '<strong>896</strong> active projects out of 1,312 total',
                    'Top stages: not started: 200, for re-targetting: 183, unknown: 175',
                    '<span style="color:#f59e0b">&#9888; 877 stale projects</span> need follow-up',
                    '<strong>3</strong> IC reviews pending'
                ]
            },
            {
                title: 'Activity & Operations', icon: '&#9889;', color: '#f472b6',
                page: 'activities',
                points: [
                    'Activity mix: <strong>88</strong> calls, <strong>0</strong> emails, <strong>3,741</strong> meetings',
                    '<strong>7,351</strong> tasks, <strong>936</strong> notes tracked'
                ]
            }
        ],

        EXEC_CHARTS: [
            { id: 'dynamic-leads-barchart',    label: 'Leads (6mo)' },
            { id: 'dynamic-revenue-barchart',   label: 'Revenue (6mo)' },
            { id: 'dynamic-deals-barchart',     label: 'Deals Created (6mo)' },
            { id: 'dynamic-activity-barchart',  label: 'Activity (6mo)' }
        ],

        EXEC_TARGET: {
            label: 'Weighted Pipeline vs Monthly Target (£100.0K)',
            current: 355944.05,
            target: 100000,
            pct: 100.0
        },

        // ── Inbound Queue ──
        INBOUND_KPIS: [
            { label: 'Critical', value: 628, accent: '#ef4444', icon: '&#9888;', subtitle: 'need immediate action' },
            { label: 'High',     value: 68,  accent: '#f59e0b', icon: '&#9650;', subtitle: 'action today' },
            { label: 'Medium',   value: 204, accent: '#3CB4AD', icon: '&#9679;', subtitle: 'this week' },
            { label: 'Low',      value: 2,   accent: '#34d399', icon: '&#9660;', subtitle: 'when convenient' }
        ],

        INBOUND_CATEGORIES: [
            { label: 'Stale Follow Up', count: 678, color: '#ef4444' },
            { label: 'Nda Request',     count: 176, color: '#f472b6' },
            { label: 'Ic Review',       count: 21,  color: '#a78bfa' },
            { label: 'Alert',           count: 9,   color: '#f59e0b' },
            { label: 'Web Signal',      count: 8,   color: '#3CB4AD' },
            { label: 'Follow Up',       count: 5,   color: '#f59e0b' },
            { label: 'Deal Update',     count: 4,   color: '#334FB4' },
            { label: 'New Lead',        count: 1,   color: '#22c55e' }
        ],

        INBOUND_SOURCES: [
            { label: 'monday',  count: 861, icon: '&#128197;' },
            { label: 'hubspot', count: 25,  icon: '&#128200;' },
            { label: 'system',  count: 9,   icon: '&#9881;' },
            { label: 'email',   count: 7,   icon: '&#9993;' }
        ],

        // ── AI Roadmap ──
        AI_KPIS: [
            { label: 'AI Items',       value: 35, accent: '#3CB4AD', icon: '&#129302;', subtitle: 'Across 7 boards' },
            { label: 'Initiatives',    value: 5,  accent: '#334FB4', icon: '&#128640;', subtitle: '' },
            { label: 'Tools Tracked',  value: 6,  accent: '#a78bfa', icon: '&#128736;', subtitle: '' },
            { label: 'Active Projects', value: 2, accent: '#22c55e', icon: '&#9881;',   subtitle: '' }
        ]
    };
})();
