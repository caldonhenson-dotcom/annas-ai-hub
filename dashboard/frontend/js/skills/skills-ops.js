/* ============================================================
   Skills — Operations Management (13 skills)
   ============================================================ */
(function () {
    'use strict';

    window.SkillsRegistry.registerBatch([
        { id: 'ops-weekly-roundup', name: 'Weekly Operations Roundup', icon: '&#128240;', category: 'ops',
          impact: 5, complexity: 'Medium', status: 'ready', timeSavedMin: 45, estimatedTime: '15-30s',
          description: 'AI-generated weekly report: per-person activity, department rollups, flags, completed and upcoming items.',
          execute: { type: 'ai-query', inputs: [
              { key: 'week', label: 'Week', type: 'select', default: 'current', options: [
                  { value: 'current', label: 'This week' }, { value: 'last', label: 'Last week' }] },
              { key: 'focus', label: 'Focus areas (optional)', type: 'textarea', placeholder: 'e.g. Deal pipeline progress, team capacity, overdue items' }
          ], buildPayload: function (i) { return { question: 'Generate a Weekly Operations Roundup for ' + i.week + ' week. Include:\n1. EXECUTIVE SUMMARY: 3-4 bullet points on key outcomes\n2. PIPELINE UPDATE: New deals, stage movements, closings\n3. TEAM ACTIVITY: Per-person summary (calls, emails, meetings, tasks completed)\n4. FLAGS: Overdue items, stale deals, SLA breaches\n5. COMPLETED: Major items completed this week\n6. UPCOMING: Key items for next week with owners\n7. METRICS: Activity vs targets\n' + (i.focus ? 'Special focus: ' + i.focus : '') + '\nUse dashboard data.', report: true }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }, { label: '&#128424; Export', handler: 'exportPdf' }] },
          requires: ['groq'],
          blocks: [{id:'ai-analyse',role:'core'},{id:'monday-read',role:'enhance'},{id:'hubspot-read',role:'enhance'},{id:'dashboard-context',role:'enhance'},{id:'pdf-export',role:'output'},{id:'email-send',role:'enhance'}],
          tags: ['weekly', 'roundup', 'operations', 'report'] },

        { id: 'ops-monday-board-audit', name: 'Monday Board Audit', icon: '&#129529;', category: 'ops',
          impact: 4, complexity: 'Medium', status: 'ready', timeSavedMin: 30, estimatedTime: '10-20s',
          description: 'Scan Monday.com boards: stale items, empty boards, boards without owners, duplicates.',
          execute: { type: 'ai-query', inputs: [],
            buildPayload: function () { return { question: 'Conduct a Monday.com board health audit. Identify:\n1. STALE ITEMS: Items with no update in 14+ days\n2. OVERDUE ITEMS: Items past their due date\n3. UNASSIGNED ITEMS: Items without an owner\n4. EMPTY/INACTIVE BOARDS: Boards with no recent activity\n5. WORKLOAD IMBALANCE: Who has too many/too few items\n\nProvide counts and specific examples for each category. Recommend cleanup actions.' }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          requires: ['groq'],
          blocks: [{id:'ai-analyse',role:'core'},{id:'monday-read',role:'enhance'}],
          tags: ['monday', 'audit', 'cleanup', 'board'] },

        { id: 'ops-team-activity-report', name: 'Team Activity Report', icon: '&#128202;', category: 'ops',
          impact: 4, complexity: 'Low', status: 'ready', timeSavedMin: 20, estimatedTime: '10-15s',
          description: 'Per-person breakdown: emails, calls, meetings, tasks completed, compared to team average.',
          execute: { type: 'ai-query', inputs: [
              { key: 'period', label: 'Period', type: 'select', default: 'this_week', options: [
                  { value: 'this_week', label: 'This week' }, { value: 'mtd', label: 'Month to date' },
                  { value: 'qtd', label: 'Quarter to date' }] },
              { key: 'team_member', label: 'Team member (or "all")', type: 'text', default: 'all' }
          ], buildPayload: function (i) { return { question: 'Generate a team activity report for ' + (i.team_member === 'all' ? 'all team members' : i.team_member) + ' for ' + i.period + '. Include: emails sent, calls made, meetings held, tasks completed, deals touched, and compare each person against the team average. Highlight top performers and anyone significantly below average. Use dashboard data.' }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          requires: ['groq'],
          blocks: [{id:'ai-analyse',role:'core'},{id:'hubspot-read',role:'enhance'},{id:'monday-read',role:'enhance'},{id:'dashboard-context',role:'enhance'}],
          tags: ['team', 'activity', 'report', 'performance'] },

        { id: 'ops-resource-utilisation', name: 'Resource Utilisation Check', icon: '&#9881;', category: 'ops',
          impact: 4, complexity: 'Medium', status: 'ready', timeSavedMin: 20, estimatedTime: '10-20s',
          description: 'Workload analysis per team member: active items, deals owned, activity level, flags.',
          execute: { type: 'ai-query', inputs: [],
            buildPayload: function () { return { question: 'Analyse team resource utilisation. For each team member:\n1. Active Monday.com items count\n2. Deals owned in pipeline\n3. Activity level this week (high/medium/low)\n4. Flag: OVER-UTILISED / BALANCED / UNDER-UTILISED\n\nRecommend any re-allocation of work. Identify single points of failure (one person owning too much).' }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          requires: ['groq'],
          blocks: [{id:'ai-analyse',role:'core'},{id:'monday-read',role:'enhance'},{id:'hubspot-read',role:'enhance'},{id:'dashboard-context',role:'enhance'}],
          tags: ['resource', 'utilisation', 'capacity', 'team'] },

        { id: 'ops-process-bottleneck', name: 'Identify Bottlenecks', icon: '&#128679;', category: 'ops',
          impact: 4, complexity: 'Medium', status: 'ready', timeSavedMin: 25, estimatedTime: '10-20s',
          description: 'AI analysis of where items get stuck, average time per stage, recommendations.',
          execute: { type: 'ai-query', inputs: [
              { key: 'area', label: 'Process area', type: 'select', default: 'ma', options: [
                  { value: 'ma', label: 'M&A Pipeline' }, { value: 'sales', label: 'Sales Process' },
                  { value: 'ops', label: 'Operations' }, { value: 'all', label: 'All Areas' }] }
          ], buildPayload: function (i) { return { question: 'Identify process bottlenecks in our ' + i.area + ' workflows. Analyse:\n1. STAGE ANALYSIS: Average time spent in each stage, where do items get stuck\n2. BOTTLENECK STAGES: Which stages have the longest dwell time\n3. VOLUME BOTTLENECKS: Where items pile up\n4. ROOT CAUSES: Why bottlenecks exist (resource constraints, dependencies, approvals)\n5. RECOMMENDATIONS: Specific actions to reduce cycle times\nUse available dashboard and pipeline data.' }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          requires: ['groq'],
          blocks: [{id:'ai-analyse',role:'core'},{id:'hubspot-read',role:'enhance'},{id:'monday-read',role:'enhance'},{id:'dashboard-context',role:'enhance'}],
          tags: ['bottleneck', 'process', 'improvement'] },

        { id: 'ops-meeting-prep-pack', name: 'Meeting Prep Pack', icon: '&#128188;', category: 'ops',
          impact: 4, complexity: 'Low', status: 'ready', timeSavedMin: 20, estimatedTime: '10-20s',
          description: 'Auto-generated briefing doc with KPIs, pipeline status, flags, and talking points.',
          execute: { type: 'ai-query', inputs: [
              { key: 'meeting_type', label: 'Meeting type', type: 'select', default: 'ops_review', options: [
                  { value: 'board', label: 'Board Meeting' }, { value: 'ops_review', label: 'Ops Review' },
                  { value: 'team', label: 'Team Meeting' }, { value: 'ic', label: 'Investment Committee' }] }
          ], buildPayload: function (i) { return { question: 'Generate a ' + i.meeting_type + ' preparation pack. Include:\n1. KEY METRICS: Relevant KPIs with period-over-period comparison\n2. PIPELINE STATUS: Current state, movements, notable deals\n3. FLAGS: Items needing attention or decision\n4. AGENDA SUGGESTIONS: Based on current state\n5. TALKING POINTS: Key messages for the meeting\n6. ACTIONS FROM LAST MEETING: Status update\nUse dashboard data.' }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }, { label: '&#128424; Export', handler: 'exportPdf' }] },
          requires: ['groq'],
          blocks: [{id:'ai-analyse',role:'core'},{id:'hubspot-read',role:'enhance'},{id:'monday-read',role:'enhance'},{id:'dashboard-context',role:'enhance'},{id:'pdf-export',role:'output'}],
          tags: ['meeting', 'prep', 'briefing'] },

        { id: 'ops-vendor-spend-tracker', name: 'Vendor Spend Tracker', icon: '&#128176;', category: 'ops',
          impact: 3, complexity: 'Medium', status: 'planned', timeSavedMin: 15, estimatedTime: '5-10s',
          description: 'Dashboard of vendor/tool spend: monthly cost, renewal dates, utilisation, savings suggestions.',
          execute: { type: 'api-call', inputs: [], buildPayload: function () { return { target: 'supabase', action: 'vendor_spend' }; }, resultType: 'json' },
          requires: ['supabase'],
          blocks: [{id:'data-read',role:'core'}],
          tags: ['vendor', 'spend', 'cost', 'tracker'] },

        { id: 'ops-onboarding-checklist', name: 'New Hire Onboarding', icon: '&#128203;', category: 'ops',
          impact: 3, complexity: 'Medium', status: 'planned', timeSavedMin: 20, estimatedTime: '10-15s',
          description: 'Creates Monday.com onboarding board, sends welcome emails, generates access request list.',
          execute: { type: 'api-call', inputs: [
              { key: 'name', label: 'New hire name', type: 'text', required: true },
              { key: 'role', label: 'Role', type: 'text', required: true },
              { key: 'start_date', label: 'Start date', type: 'text', required: true }
          ], buildPayload: function (i) { return { target: 'monday', action: 'create_onboarding', name: i.name, role: i.role, start_date: i.start_date }; },
            resultType: 'json' },
          requires: ['monday'],
          blocks: [{id:'monday-write',role:'core'}],
          tags: ['onboarding', 'new-hire', 'checklist'] },

        { id: 'ops-quarterly-review-pack', name: 'Quarterly Review Pack', icon: '&#128197;', category: 'ops',
          impact: 5, complexity: 'High', status: 'ready', timeSavedMin: 60, estimatedTime: '25-45s',
          description: 'Comprehensive quarterly report: revenue, deals, pipeline, team performance, AI insights.',
          execute: { type: 'ai-query', inputs: [
              { key: 'quarter', label: 'Quarter', type: 'text', required: true, placeholder: 'e.g. Q1 2026' }
          ], buildPayload: function (i) { return { question: 'Generate a comprehensive Quarterly Review Pack for ' + i.quarter + '. Structure:\n1. EXECUTIVE SUMMARY\n2. REVENUE PERFORMANCE: Actual vs target, growth vs prior quarter\n3. DEAL FLOW: New deals, stage progression, closings, losses\n4. PIPELINE HEALTH: Current pipeline, coverage ratio, velocity\n5. TEAM PERFORMANCE: Activity metrics, individual contributions\n6. M&A ACTIVITY: Deals in progress, CDD status, upcoming completions\n7. OPERATIONAL HIGHLIGHTS: Process improvements, system changes\n8. KEY RISKS: Top 5 risks and mitigations\n9. AI INSIGHTS: Pattern observations and recommendations\n10. NEXT QUARTER PRIORITIES\nUse dashboard data.', report: true }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }, { label: '&#128424; Export', handler: 'exportPdf' }] },
          requires: ['groq'],
          blocks: [{id:'ai-analyse',role:'core'},{id:'hubspot-read',role:'enhance'},{id:'monday-read',role:'enhance'},{id:'dashboard-context',role:'enhance'},{id:'pdf-export',role:'output'}],
          tags: ['quarterly', 'review', 'report', 'comprehensive'] },

        { id: 'ops-daily-standup-digest', name: 'Daily Standup Digest', icon: '&#127749;', category: 'ops',
          impact: 3, complexity: 'Low', status: 'ready', timeSavedMin: 10, estimatedTime: '8-12s',
          description: 'Brief morning digest: yesterday completions, today priorities, blockers, deals needing attention.',
          execute: { type: 'ai-query', inputs: [],
            buildPayload: function () { return { question: 'Generate a daily standup digest. Include:\n1. YESTERDAY: Key completions and outcomes\n2. TODAY: Top priority items across all team members\n3. BLOCKERS: Any items that are blocked or need escalation\n4. DEALS NEEDING ATTENTION: Deals with upcoming deadlines or stale activity\n5. CALENDAR: Key meetings today\nKeep it concise (under 200 words). Use dashboard data.' }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          requires: ['groq'],
          blocks: [{id:'ai-analyse',role:'core'},{id:'hubspot-read',role:'enhance'},{id:'monday-read',role:'enhance'},{id:'dashboard-context',role:'enhance'}],
          tags: ['standup', 'daily', 'digest', 'morning'] },

        { id: 'ops-sla-monitor', name: 'SLA Monitor', icon: '&#9201;', category: 'ops',
          impact: 3, complexity: 'Medium', status: 'ready', timeSavedMin: 10, estimatedTime: '5-10s',
          description: 'Check response times on new leads and flag SLA breaches.',
          execute: { type: 'ai-query', inputs: [
              { key: 'sla_hours', label: 'SLA response time (hours)', type: 'number', default: '24' }
          ], buildPayload: function (i) { return { question: 'Monitor SLA compliance. Our target is to respond to new inbound leads within ' + i.sla_hours + ' hours. Using dashboard data:\n1. How many new leads received this week?\n2. Average response time\n3. SLA compliance rate (%)\n4. List any breaches with lead name, source, and response time\n5. Trend: Is compliance improving or declining?' }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          requires: ['groq'],
          blocks: [{id:'ai-analyse',role:'core'},{id:'hubspot-read',role:'enhance'},{id:'dashboard-context',role:'enhance'}],
          tags: ['sla', 'monitor', 'compliance', 'response'] },

        { id: 'ops-kpi-alert', name: 'KPI Alert Engine', icon: '&#128680;', category: 'ops',
          impact: 3, complexity: 'Low', status: 'ready', timeSavedMin: 5, estimatedTime: '5-8s',
          description: 'Check KPIs against thresholds and flag any anomalies or concerning trends.',
          execute: { type: 'ai-query', inputs: [],
            buildPayload: function () { return { question: 'Check our KPIs against healthy thresholds and flag any concerns:\n- Pipeline coverage ratio (healthy: >3x)\n- Win rate (healthy: >25%)\n- Average deal velocity (healthy: <90 days)\n- Team activity levels (healthy: >10 activities/person/week)\n- Lead response time (healthy: <24h)\n- Stale deal percentage (healthy: <15%)\n\nFor each KPI: current value, status (GREEN/AMBER/RED), and recommended action if not green. Use dashboard data.' }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          requires: ['groq'],
          blocks: [{id:'ai-analyse',role:'core'},{id:'hubspot-read',role:'enhance'},{id:'dashboard-context',role:'enhance'}],
          tags: ['kpi', 'alert', 'threshold', 'monitoring'] },

        { id: 'ops-cost-per-acquisition', name: 'CPA Report', icon: '&#129534;', category: 'ops',
          impact: 3, complexity: 'Medium', status: 'planned', timeSavedMin: 20, estimatedTime: '10-15s',
          description: 'Cost per acquisition by channel, compared to LTV estimates, budget recommendations.',
          execute: { type: 'ai-query', inputs: [
              { key: 'spend_data', label: 'Marketing spend by channel (optional)', type: 'textarea', placeholder: 'e.g. LinkedIn: £2000/mo, Events: £5000/mo, Content: £1000/mo' }
          ], buildPayload: function (i) { return { question: 'Generate a Cost Per Acquisition report. ' + (i.spend_data ? 'Spend data: ' + i.spend_data + '. ' : '') + 'Analyse:\n1. CPA by channel/source\n2. Conversion rates through the funnel\n3. Estimated LTV by deal source\n4. ROI by channel\n5. Budget allocation recommendations\nUse dashboard pipeline data for conversion analysis.' }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          requires: ['groq'],
          blocks: [{id:'ai-analyse',role:'core'},{id:'hubspot-read',role:'enhance'},{id:'dashboard-context',role:'enhance'}],
          tags: ['cpa', 'acquisition', 'cost', 'marketing'] }
    ]);
})();
