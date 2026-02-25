/* ============================================================
   Skills — Deal Pipeline Management (12 skills)
   ============================================================ */
(function () {
    'use strict';

    window.SkillsRegistry.registerBatch([
        { id: 'acquisition-opportunity-finder', name: 'Acquisition Opportunity Finder', icon: '&#128270;', category: 'pipeline',
          impact: 5, complexity: 'High', status: 'ready', timeSavedMin: 120, estimatedTime: '30-60s',
          description: 'AI scans for businesses matching acquisition criteria: sector, revenue, geography, ownership. Outputs ranked list with fit scores.',
          execute: { type: 'ai-query', inputs: [
              { key: 'sector', label: 'Target sector', type: 'text', required: true, placeholder: 'e.g. E-commerce, SaaS, Health & Wellness' },
              { key: 'revenue', label: 'Revenue range', type: 'select', default: '3-10m', options: [
                  { value: '1-3m', label: '£1-3M' }, { value: '3-10m', label: '£3-10M' },
                  { value: '10-25m', label: '£10-25M' }, { value: '25m+', label: '£25M+' }] },
              { key: 'geography', label: 'Geography', type: 'select', default: 'uk', options: [
                  { value: 'uk', label: 'UK' }, { value: 'europe', label: 'Europe' }, { value: 'global', label: 'Global' }] },
              { key: 'criteria', label: 'Additional criteria (optional)', type: 'textarea', placeholder: 'e.g. Profitable, owner-managed, strong brand, repeat revenue model' }
          ], buildPayload: function (i) { return { question: 'Identify 10-15 acquisition opportunities for eComplete in the ' + i.sector + ' sector, ' + i.revenue + ' revenue range, ' + i.geography + ' geography. ' + (i.criteria ? 'Additional criteria: ' + i.criteria + '. ' : '') + '\nFor each opportunity provide:\n1. Company name and brief description\n2. Estimated revenue and growth\n3. Ownership type (PE-backed, founder-led, corporate)\n4. Key strengths\n5. FIT SCORE (1-10) with justification\n6. Approach strategy suggestion\n\nRank by fit score descending. Focus on actionable targets that could realistically be acquired.', report: true }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }, { label: '&#128424; Export', handler: 'exportPdf' }] },
          requires: ['groq'], tags: ['acquisition', 'opportunity', 'sourcing', 'pipeline'] },

        { id: 'opportunity-reviewer', name: 'Opportunity Reviewer', icon: '&#128209;', category: 'pipeline',
          impact: 5, complexity: 'Medium', status: 'ready', timeSavedMin: 60, estimatedTime: '20-35s',
          description: 'Scores an acquisition opportunity against eComplete\'s criteria matrix with Go/No-Go recommendation.',
          execute: { type: 'ai-query', inputs: [
              { key: 'company', label: 'Company name', type: 'text', required: true },
              { key: 'data', label: 'Available data about the opportunity', type: 'textarea', required: true, placeholder: 'Revenue, sector, ownership, any known details...' }
          ], buildPayload: function (i) { return { question: 'Review this acquisition opportunity for eComplete: ' + i.company + '.\n\nData provided:\n' + i.data + '\n\nScore against eComplete\'s acquisition criteria:\n1. STRATEGIC FIT (1-10): Sector alignment, portfolio synergies\n2. FINANCIAL ATTRACTIVENESS (1-10): Revenue quality, margins, growth\n3. OPERATIONAL QUALITY (1-10): Team, processes, scalability\n4. MARKET POSITION (1-10): Competitive moat, brand strength\n5. DEAL FEASIBILITY (1-10): Willing seller signals, valuation expectations, complexity\n\nOVERALL SCORE and RECOMMENDATION: Strong Go / Conditional Go / Watch / No-Go\nKEY RISKS and MITIGATIONS\nSUGGESTED NEXT STEPS', report: true }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }, { label: '&#128424; Export', handler: 'exportPdf' }] },
          requires: ['groq'], tags: ['opportunity', 'review', 'scoring', 'ma'] },

        { id: 'deal-create-new', name: 'Create New Deal', icon: '&#10133;', category: 'pipeline',
          impact: 3, complexity: 'Low', status: 'planned', timeSavedMin: 10, estimatedTime: '3-5s',
          description: 'Create a new deal in HubSpot + Monday.com project board with initial stage and owner.',
          execute: { type: 'api-call', inputs: [
              { key: 'company', label: 'Company name', type: 'text', required: true },
              { key: 'value', label: 'Estimated deal value', type: 'text', placeholder: 'e.g. £5M' },
              { key: 'source', label: 'Source', type: 'select', default: 'outbound', options: [
                  { value: 'outbound', label: 'Outbound' }, { value: 'inbound', label: 'Inbound' },
                  { value: 'referral', label: 'Referral' }, { value: 'broker', label: 'Broker' }] }
          ], buildPayload: function (i) { return { target: 'hubspot', path: '/crm/v3/objects/deals', method: 'POST', body: { properties: { dealname: i.company, amount: i.value, pipeline: 'default', dealstage: 'qualifiedtobuy', deal_source: i.source } } }; },
            resultType: 'json' },
          requires: ['hubspot'], tags: ['deal', 'create', 'pipeline'] },

        { id: 'deal-advance-stage', name: 'Advance Deal Stage', icon: '&#9654;', category: 'pipeline',
          impact: 2, complexity: 'Low', status: 'planned', timeSavedMin: 5, estimatedTime: '2-3s',
          description: 'Move a deal to the next pipeline stage in HubSpot and Monday.com.',
          execute: { type: 'api-call', inputs: [
              { key: 'deal_id', label: 'HubSpot Deal ID', type: 'text', required: true },
              { key: 'new_stage', label: 'New stage', type: 'select', default: 'nda', options: [
                  { value: 'qualified', label: 'Qualified' }, { value: 'nda', label: 'NDA' },
                  { value: 'cdd', label: 'CDD' }, { value: 'loi', label: 'LOI' },
                  { value: 'completion', label: 'Completion' }] }
          ], buildPayload: function (i) { return { target: 'hubspot', path: '/crm/v3/objects/deals/' + i.deal_id, method: 'PATCH', body: { properties: { dealstage: i.new_stage } } }; },
            resultType: 'json' },
          requires: ['hubspot'], tags: ['deal', 'stage', 'advance'] },

        { id: 'deal-stale-report', name: 'Stale Deals Report', icon: '&#9203;', category: 'pipeline',
          impact: 4, complexity: 'Low', status: 'ready', timeSavedMin: 15, estimatedTime: '10-15s',
          description: 'AI identifies stale deals with no activity and suggests next actions per deal.',
          execute: { type: 'ai-query', inputs: [
              { key: 'days', label: 'Days without activity', type: 'select', default: '14', options: [
                  { value: '7', label: '7+ days' }, { value: '14', label: '14+ days' }, { value: '30', label: '30+ days' }] }
          ], buildPayload: function (i) { return { question: 'Analyse our deal pipeline and identify stale deals (no activity for ' + i.days + '+ days). For each stale deal provide: deal name, current stage, days since last activity, owner, estimated value, and a SPECIFIC recommended next action. Prioritise by deal value and staleness. Use the dashboard data available.' }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          requires: ['groq'], tags: ['stale', 'deals', 'pipeline', 'action'] },

        { id: 'deal-pipeline-snapshot', name: 'Pipeline Snapshot', icon: '&#128248;', category: 'pipeline',
          impact: 3, complexity: 'Low', status: 'ready', timeSavedMin: 10, estimatedTime: '8-15s',
          description: 'Current pipeline summary: deals by stage, total value, weighted value, win rate, coverage.',
          execute: { type: 'ai-query', inputs: [],
            buildPayload: function () { return { question: 'Generate a pipeline snapshot report. Include: total deals by stage (Lead, Qualified, NDA, CDD, LOI, Completion), total pipeline value, weighted pipeline value, current win rate, pipeline coverage ratio (target 3x), average deal size, and notable movements this month. Use the dashboard data.' }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          requires: ['groq'], tags: ['pipeline', 'snapshot', 'summary'] },

        { id: 'deal-forecast-90day', name: '90-Day Forecast', icon: '&#128302;', category: 'pipeline',
          impact: 4, complexity: 'Medium', status: 'ready', timeSavedMin: 20, estimatedTime: '10-20s',
          description: 'AI revenue forecast using pipeline deals, win probabilities, and historical conversion rates.',
          execute: { type: 'ai-query', inputs: [],
            buildPayload: function () { return { question: 'Generate a 90-day revenue forecast based on our current pipeline. For each deal in advanced stages (NDA+), estimate: probability of closing, expected close date, and weighted value. Provide three scenarios: BEST CASE, EXPECTED, WORST CASE with total forecasted revenue for each. Include assumptions and key risks to the forecast.' }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }, { label: '&#128424; Export', handler: 'exportPdf' }] },
          requires: ['groq'], tags: ['forecast', 'revenue', 'pipeline', '90-day'] },

        { id: 'deal-ic-scorecard-generate', name: 'Generate IC Scorecard', icon: '&#127942;', category: 'pipeline',
          impact: 4, complexity: 'Medium', status: 'ready', timeSavedMin: 30, estimatedTime: '15-25s',
          description: 'Pre-populated Investment Committee scorecard with CDD data, financials, and market position.',
          execute: { type: 'ai-query', inputs: [
              { key: 'deal', label: 'Deal/project name', type: 'text', required: true },
              { key: 'data', label: 'Available deal data', type: 'textarea', required: true, placeholder: 'Revenue, sector, CDD findings, key risks, valuation expectations...' }
          ], buildPayload: function (i) { return { question: 'Generate an Investment Committee Scorecard for ' + i.deal + '. Score each dimension 1-10:\n1. MARKET ATTRACTIVENESS: Size, growth, trends\n2. COMPETITIVE POSITION: Moat, differentiation, market share\n3. FINANCIAL QUALITY: Revenue growth, margins, cash generation\n4. MANAGEMENT TEAM: Depth, track record, retention risk\n5. STRATEGIC FIT: Portfolio synergies, platform potential\n6. DEAL TERMS: Valuation, structure, conditions\n7. INTEGRATION RISK: Complexity, timeline, cultural fit\n\nOVERALL SCORE with GO/CONDITIONAL/NO-GO recommendation.\n\nData: ' + i.data, report: true }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }, { label: '&#128424; Export', handler: 'exportPdf' }] },
          requires: ['groq'], tags: ['ic', 'scorecard', 'investment-committee'] },

        { id: 'deal-loi-checklist', name: 'LOI Prep Checklist', icon: '&#9989;', category: 'pipeline',
          impact: 3, complexity: 'Low', status: 'ready', timeSavedMin: 15, estimatedTime: '8-12s',
          description: 'Auto-generated LOI preparation checklist: CDD status, NDA status, key terms to negotiate.',
          execute: { type: 'ai-query', inputs: [
              { key: 'deal', label: 'Deal name', type: 'text', required: true },
              { key: 'status', label: 'Current deal status summary', type: 'textarea', placeholder: 'e.g. NDA signed, CDD 80% complete, valuation range £5-7M discussed' }
          ], buildPayload: function (i) { return { question: 'Generate an LOI Preparation Checklist for ' + i.deal + '. Current status: ' + (i.status || 'unknown') + '.\n\nInclude:\n1. PRE-LOI CHECKLIST: CDD complete? NDA in place? Valuation agreed? Key terms discussed?\n2. LOI KEY TERMS: Price/range, payment structure, exclusivity period, conditions precedent, timeline to completion\n3. NEGOTIATION STRATEGY: What to push on, what to concede, walk-away points\n4. NEXT STEPS: Specific actions with owners and deadlines\n5. RISKS: Deal-breakers to watch for' }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          requires: ['groq'], tags: ['loi', 'checklist', 'preparation'] },

        { id: 'deal-health-check', name: 'Deal Health Check', icon: '&#129657;', category: 'pipeline',
          impact: 3, complexity: 'Low', status: 'ready', timeSavedMin: 15, estimatedTime: '10-15s',
          description: 'AI assessment: engagement level, stage velocity, risk factors, probability of closing.',
          execute: { type: 'ai-query', inputs: [
              { key: 'deal', label: 'Deal name', type: 'text', required: true },
              { key: 'details', label: 'Deal details', type: 'textarea', required: true, placeholder: 'Stage, days in stage, last activity, value, key contacts, any issues...' }
          ], buildPayload: function (i) { return { question: 'Conduct a Deal Health Check for ' + i.deal + '. Details: ' + i.details + '\n\nAssess:\n1. ENGAGEMENT LEVEL: How active is the counterparty? (Hot/Warm/Cold)\n2. VELOCITY: Is the deal moving at expected pace? Days in current stage vs average\n3. RISK FACTORS: What could derail this deal?\n4. PROBABILITY: Estimated close probability (%)\n5. RECOMMENDED ACTIONS: Top 3 actions to move this forward\n6. OVERALL HEALTH: Green/Amber/Red with justification' }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          requires: ['groq'], tags: ['health', 'deal', 'assessment'] },

        { id: 'deal-win-loss-analysis', name: 'Win/Loss Analysis', icon: '&#128201;', category: 'pipeline',
          impact: 4, complexity: 'Medium', status: 'ready', timeSavedMin: 25, estimatedTime: '10-20s',
          description: 'Analyse won vs lost deals: common factors, drop-off stages, time-to-close, AI insights.',
          execute: { type: 'ai-query', inputs: [
              { key: 'period', label: 'Period', type: 'select', default: 'qtd', options: [
                  { value: 'qtd', label: 'This quarter' }, { value: 'ytd', label: 'Year to date' },
                  { value: 'last_year', label: 'Last year' }] }
          ], buildPayload: function () { return { question: 'Analyse our deal pipeline win/loss patterns using dashboard data. Include: won deal count & total value, lost deal count & value, win rate by stage, average time-to-close, most common loss reasons, stage where deals most frequently die, and actionable insights to improve win rate.' }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          requires: ['groq'], tags: ['win-loss', 'analysis', 'pipeline'] },

        { id: 'deal-handover-pack', name: 'Deal Handover Pack', icon: '&#128188;', category: 'pipeline',
          impact: 4, complexity: 'Medium', status: 'ready', timeSavedMin: 30, estimatedTime: '15-25s',
          description: 'Complete deal summary for handover: contacts, history, CDD status, outstanding items.',
          execute: { type: 'ai-query', inputs: [
              { key: 'deal', label: 'Deal name', type: 'text', required: true },
              { key: 'data', label: 'All available deal data', type: 'textarea', required: true, placeholder: 'Contacts, activity history, CDD status, NDA status, financial data, next steps...' }
          ], buildPayload: function (i) { return { question: 'Generate a Deal Handover Pack for ' + i.deal + '. Structure:\n1. DEAL OVERVIEW: Company, sector, value, current stage\n2. KEY CONTACTS: Names, roles, relationship status, last interaction\n3. ACTIVITY TIMELINE: Key events and milestones chronologically\n4. CDD STATUS: What is complete, what is outstanding\n5. NDA STATUS: Signed/pending, key terms\n6. FINANCIAL SUMMARY: Known financials\n7. OUTSTANDING ITEMS: What needs to happen next\n8. RISK REGISTER: Active risks\n9. HANDOVER NOTES: Critical context the new owner needs to know\n\nData: ' + i.data, report: true }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }, { label: '&#128424; Export', handler: 'exportPdf' }] },
          requires: ['groq'], tags: ['handover', 'deal', 'pack', 'summary'] }
    ]);
})();
