/* ============================================================
   Skills — Board Reporting, Intelligence, Data, Portfolio
   (Categories 7-10: 28 skills)
   ============================================================ */
(function () {
    'use strict';

    // ---- Category 7: Board & Investor Reporting (8 skills) ----
    window.SkillsRegistry.registerBatch([
        { id: 'presentation-builder', name: 'Presentation Builder', icon: '&#128202;', category: 'board-reporting',
          impact: 5, complexity: 'Medium', status: 'ready', timeSavedMin: 90, estimatedTime: '25-45s',
          description: 'Generates structured slide content for board meetings, ops reviews, or investor updates with talking points.',
          execute: { type: 'ai-query', inputs: [
              { key: 'type', label: 'Presentation type', type: 'select', default: 'board', options: [
                  { value: 'board', label: 'Board Meeting' }, { value: 'ops_review', label: 'Ops Review' },
                  { value: 'investor_update', label: 'Investor Update' }, { value: 'team_allhands', label: 'Team All-Hands' }] },
              { key: 'period', label: 'Period to cover', type: 'text', required: true, placeholder: 'e.g. February 2026, Q1 2026' },
              { key: 'audience', label: 'Audience', type: 'text', placeholder: 'e.g. Board of directors, PE investors, full team' },
              { key: 'key_messages', label: 'Key messages to emphasise', type: 'textarea', placeholder: 'e.g. Strong pipeline growth, 2 deals in LOI stage, team expansion planned' }
          ], buildPayload: function (i) { return { question: 'Build a ' + i.type + ' presentation for ' + i.period + (i.audience ? ' (audience: ' + i.audience + ')' : '') + '. Generate slide-by-slide content (10-15 slides):\n\nFor each slide provide:\n- SLIDE TITLE\n- KEY CONTENT: Bullet points and data (using dashboard data where available)\n- TALKING POINTS: What to say when presenting this slide\n- VISUAL SUGGESTION: Chart type or layout recommendation\n\n' + (i.key_messages ? 'Key messages to weave in: ' + i.key_messages : '') + '\n\nMake it boardroom-ready: concise, data-driven, with clear narrative flow.', report: true }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }, { label: '&#128424; Export', handler: 'exportPdf' }] },
          blocks: [{id:'ai-analyse',role:'core'},{id:'hubspot-read',role:'enhance'},{id:'monday-read',role:'enhance'},{id:'dashboard-context',role:'enhance'},{id:'pdf-export',role:'output'}], requires: ['groq'], tags: ['presentation', 'slides', 'board', 'investor'] },

        { id: 'pitch-deck-builder', name: 'Pitch Deck Builder', icon: '&#127919;', category: 'board-reporting',
          impact: 5, complexity: 'High', status: 'ready', timeSavedMin: 120, estimatedTime: '30-60s',
          description: 'Creates pillar-specific pitch decks with live data, competitive positioning, and market opportunity.',
          execute: { type: 'ai-query', inputs: [
              { key: 'pillar', label: 'Business pillar', type: 'select', default: 'ma_advisory', options: [
                  { value: 'ma_advisory', label: 'M&A Advisory' }, { value: 'portfolio_brands', label: 'Portfolio Brands' },
                  { value: 'new_vertical', label: 'New Vertical' }, { value: 'ecomplete_group', label: 'eComplete Group' }] },
              { key: 'audience', label: 'Target audience', type: 'select', default: 'investor', options: [
                  { value: 'investor', label: 'Investor / PE' }, { value: 'partner', label: 'Strategic Partner' },
                  { value: 'vendor', label: 'Vendor / Supplier' }, { value: 'acquisition_target', label: 'Acquisition Target' }] },
              { key: 'key_message', label: 'Key message / thesis', type: 'textarea', required: true, placeholder: 'e.g. eComplete has built a proven M&A platform generating 3x returns for investors through strategic e-commerce acquisitions' }
          ], buildPayload: function (i) { return { question: 'Build a pitch deck (12-15 slides) for eComplete\'s ' + i.pillar + ' pillar, targeting ' + i.audience + '. Key thesis: ' + i.key_message + '\n\nFor each slide:\n- SLIDE TITLE\n- CONTENT: Data points, metrics, evidence\n- NARRATIVE: Story being told\n- VISUAL: Recommended chart/graphic\n\nInclude: Cover, Problem/Opportunity, Solution/Approach, Market Size, Traction/Track Record, Team, Competitive Advantage, Financial Performance, Growth Strategy, Case Studies, Investment Proposition (if investor), Partnership Value (if partner), Ask/Next Steps.\n\nUse dashboard data for pipeline, deal flow, and performance metrics.', report: true }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }, { label: '&#128424; Export', handler: 'exportPdf' }] },
          blocks: [{id:'ai-analyse',role:'core'},{id:'hubspot-read',role:'enhance'},{id:'monday-read',role:'enhance'},{id:'dashboard-context',role:'enhance'},{id:'pdf-export',role:'output'}], requires: ['groq'], tags: ['pitch-deck', 'pillar', 'investor', 'presentation'] },

        { id: 'board-monthly-report', name: 'Monthly Board Report', icon: '&#128200;', category: 'board-reporting',
          impact: 5, complexity: 'High', status: 'ready', timeSavedMin: 90, estimatedTime: '25-40s',
          description: 'Branded board report: executive summary, financials, pipeline, M&A update, team, risks.',
          execute: { type: 'ai-query', inputs: [
              { key: 'month', label: 'Month', type: 'text', required: true, placeholder: 'e.g. February 2026' }
          ], buildPayload: function (i) { return { question: 'Generate a Monthly Board Report for ' + i.month + ':\n1. EXECUTIVE SUMMARY (3-5 key bullet points)\n2. FINANCIAL PERFORMANCE: Revenue, pipeline value, deal completions\n3. DEAL PIPELINE: Stage breakdown, movements, new deals\n4. M&A UPDATE: Active deals status, CDD progress, upcoming milestones\n5. TEAM PERFORMANCE: Activity metrics, headcount, key hires\n6. PORTFOLIO UPDATE: Portfolio company performance\n7. RISK REGISTER: Top 5 risks with RAG status\n8. NEXT MONTH OUTLOOK\nUse dashboard data. Make it concise and board-ready.', report: true }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }, { label: '&#128424; Export', handler: 'exportPdf' }] },
          blocks: [{id:'ai-analyse',role:'core'},{id:'hubspot-read',role:'enhance'},{id:'monday-read',role:'enhance'},{id:'dashboard-context',role:'enhance'},{id:'pdf-export',role:'output'}], requires: ['groq'], tags: ['board', 'monthly', 'report'] },

        { id: 'board-deal-flow-summary', name: 'Deal Flow Summary', icon: '&#128260;', category: 'board-reporting',
          impact: 4, complexity: 'Low', status: 'ready', timeSavedMin: 30, estimatedTime: '10-15s',
          description: 'Deal flow metrics with period comparison: new deals, progression, conversion, source breakdown.',
          execute: { type: 'ai-query', inputs: [
              { key: 'period', label: 'Period', type: 'select', default: 'mtd', options: [
                  { value: 'wtd', label: 'This week' }, { value: 'mtd', label: 'Month to date' }, { value: 'qtd', label: 'Quarter to date' }] }
          ], buildPayload: function (i) { return { question: 'Generate a Deal Flow Summary for ' + i.period + '. Include: new deals received, deals progressed (by stage), deals closed (won/lost), conversion rates, deal source breakdown, and period-over-period comparison. Use dashboard data.' }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          blocks: [{id:'ai-analyse',role:'core'},{id:'hubspot-read',role:'enhance'},{id:'dashboard-context',role:'enhance'},{id:'clipboard-copy',role:'output'}], requires: ['groq'], tags: ['deal-flow', 'summary', 'board'] },

        { id: 'board-investor-memo', name: 'Draft Investor Memo', icon: '&#128196;', category: 'board-reporting',
          impact: 4, complexity: 'High', status: 'ready', timeSavedMin: 45, estimatedTime: '20-35s',
          description: 'AI-drafted investor memo or information memorandum with financials and investment rationale.',
          execute: { type: 'ai-query', inputs: [
              { key: 'deal', label: 'Deal name', type: 'text', required: true },
              { key: 'type', label: 'Memo type', type: 'select', default: 'teaser', options: [
                  { value: 'teaser', label: 'Teaser / 1-pager' }, { value: 'full_im', label: 'Full Information Memorandum' }] },
              { key: 'data', label: 'Deal data', type: 'textarea', required: true }
          ], buildPayload: function (i) { return { question: 'Draft a ' + i.type + ' for ' + i.deal + '. ' + (i.type === 'teaser' ? 'Keep to 1 page: company overview, key highlights, financial summary, investment rationale, next steps.' : 'Full IM structure: exec summary, company overview, market analysis, financial performance, growth strategy, management team, investment highlights, key risks, valuation context.') + '\nData: ' + i.data, report: true }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }, { label: '&#128424; Export', handler: 'exportPdf' }] },
          blocks: [{id:'ai-draft',role:'core'},{id:'hubspot-read',role:'enhance'},{id:'dashboard-context',role:'enhance'},{id:'pdf-export',role:'output'}], requires: ['groq'], tags: ['investor', 'memo', 'teaser', 'im'] },

        { id: 'board-pipeline-presentation', name: 'Pipeline Presentation Data', icon: '&#128202;', category: 'board-reporting',
          impact: 3, complexity: 'Low', status: 'ready', timeSavedMin: 20, estimatedTime: '8-15s',
          description: 'Presentation-ready pipeline data: stage funnel, value breakdown, projections.',
          execute: { type: 'ai-query', inputs: [],
            buildPayload: function () { return { question: 'Generate presentation-ready pipeline data. Include formatted for slides:\n1. Stage funnel with counts and values\n2. Pipeline value breakdown by sector\n3. Top 10 deals by value with stage and probability\n4. Projected closings for next 90 days\n5. YoY comparison metrics\nFormat each as a data table that can be pasted into PowerPoint.' }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          blocks: [{id:'ai-analyse',role:'core'},{id:'hubspot-read',role:'enhance'},{id:'dashboard-context',role:'enhance'},{id:'clipboard-copy',role:'output'}], requires: ['groq'], tags: ['pipeline', 'presentation', 'slides'] },

        { id: 'board-risk-dashboard', name: 'Risk Dashboard', icon: '&#9888;', category: 'board-reporting',
          impact: 3, complexity: 'Medium', status: 'ready', timeSavedMin: 15, estimatedTime: '10-15s',
          description: 'Consolidated risk view: deal, operational, pipeline, compliance risks with RAG status.',
          execute: { type: 'ai-query', inputs: [],
            buildPayload: function () { return { question: 'Generate a consolidated Risk Dashboard. Assess risks across:\n1. DEAL RISKS: Specific deal-level concerns\n2. PIPELINE RISKS: Coverage, concentration, velocity\n3. OPERATIONAL RISKS: Team, process, capacity\n4. MARKET RISKS: Sector, economic, regulatory\n5. COMPLIANCE RISKS: AML, GDPR, regulatory\nFor each: description, RAG status (Red/Amber/Green), trend (improving/stable/worsening), mitigation action.' }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          blocks: [{id:'ai-analyse',role:'core'},{id:'dashboard-context',role:'enhance'},{id:'clipboard-copy',role:'output'}], requires: ['groq'], tags: ['risk', 'dashboard', 'rag', 'compliance'] },

        { id: 'board-meeting-minutes', name: 'Draft Board Minutes', icon: '&#9998;', category: 'board-reporting',
          impact: 4, complexity: 'Low', status: 'ready', timeSavedMin: 30, estimatedTime: '10-20s',
          description: 'Structure rough meeting notes into formal board minutes with decisions and action items.',
          execute: { type: 'ai-query', inputs: [
              { key: 'notes', label: 'Rough meeting notes', type: 'textarea', required: true },
              { key: 'attendees', label: 'Attendees', type: 'text', required: true }
          ], buildPayload: function (i) { return { question: 'Structure these rough meeting notes into formal board minutes.\nAttendees: ' + i.attendees + '\n\nFormat:\n1. MEETING DETAILS: Date, attendees, apologies\n2. MINUTES OF PREVIOUS MEETING: Matters arising\n3. DISCUSSION ITEMS: Each agenda topic with key discussion points\n4. DECISIONS: Clearly stated decisions with voting if applicable\n5. ACTION ITEMS: Action, owner, deadline\n6. ITEMS FOR NEXT MEETING\n7. DATE OF NEXT MEETING\n\nNotes: ' + i.notes }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }, { label: '&#128424; Export', handler: 'exportPdf' }] },
          blocks: [{id:'ai-draft',role:'core'},{id:'clipboard-copy',role:'output'}], requires: ['groq'], tags: ['minutes', 'board', 'meeting', 'formal'] }
    ]);

    // ---- Category 8: Market Intelligence (8 skills) ----
    window.SkillsRegistry.registerBatch([
        { id: 'intel-competitor-monitor', name: 'Monitor Competitors', icon: '&#128225;', category: 'intel',
          impact: 4, complexity: 'Medium', status: 'ready', timeSavedMin: 30, estimatedTime: '15-25s',
          description: 'Weekly competitor digest: new filings, website changes, job postings, press mentions.',
          execute: { type: 'ai-query', inputs: [
              { key: 'competitors', label: 'Competitor names', type: 'textarea', required: true, placeholder: 'One per line' }
          ], buildPayload: function (i) { return { question: 'Generate a competitor monitoring digest for these companies:\n' + i.competitors + '\n\nFor each competitor report on:\n1. Recent news/press mentions\n2. Companies House filings (any new?)\n3. Job postings (hiring signals)\n4. Leadership changes\n5. Product/service launches\n6. M&A activity\n7. Overall threat assessment\n\nHighlight anything that requires immediate attention.' }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          blocks: [{id:'ai-analyse',role:'core'},{id:'web-fetch',role:'enhance'},{id:'clipboard-copy',role:'output'}], requires: ['groq'], tags: ['competitor', 'monitor', 'intelligence'] },

        { id: 'intel-industry-news', name: 'Industry News Digest', icon: '&#128240;', category: 'intel',
          impact: 3, complexity: 'Low', status: 'ready', timeSavedMin: 20, estimatedTime: '10-20s',
          description: 'Curated news digest: M&A transactions, funding rounds, regulatory changes in relevant sectors.',
          execute: { type: 'ai-query', inputs: [
              { key: 'sectors', label: 'Sectors of interest', type: 'text', required: true, placeholder: 'e.g. E-commerce, Health & Wellness, SaaS' }
          ], buildPayload: function (i) { return { question: 'Generate a curated industry news digest for ' + i.sectors + ' sectors. Include:\n1. M&A TRANSACTIONS: Recent deals with values and multiples\n2. FUNDING ROUNDS: Notable raises\n3. REGULATORY CHANGES: New regulations affecting these sectors\n4. MARKET TRENDS: Emerging patterns\n5. NOTABLE EXITS: Recent exits and returns\n6. IMPLICATIONS FOR ECOMPLETE: How each item affects our strategy' }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          blocks: [{id:'ai-analyse',role:'core'},{id:'web-fetch',role:'enhance'},{id:'clipboard-copy',role:'output'}], requires: ['groq'], tags: ['news', 'industry', 'digest', 'trends'] },

        { id: 'intel-companies-house-watch', name: 'Companies House Watchlist', icon: '&#128065;', category: 'intel',
          impact: 3, complexity: 'Medium', status: 'planned', timeSavedMin: 10, estimatedTime: '5-10s',
          description: 'Monitor Companies House for new filings, director changes, and charges on watched companies.',
          execute: { type: 'api-call', inputs: [
              { key: 'companies', label: 'Company numbers', type: 'text', required: true }
          ], buildPayload: function (i) { return { target: 'companies-house', action: 'watch', companies: i.companies.split(',').map(function(s){return s.trim();}) }; },
            resultType: 'json' },
          blocks: [{id:'companies-house-lookup',role:'core'},{id:'notification',role:'output'}], requires: ['companies-house'], tags: ['companies-house', 'watch', 'filings'] },

        { id: 'intel-market-sizing', name: 'Quick Market Sizing', icon: '&#127758;', category: 'intel',
          impact: 4, complexity: 'Medium', status: 'ready', timeSavedMin: 30, estimatedTime: '15-25s',
          description: 'Top-down and bottom-up market size estimate with sources, growth rate, key drivers.',
          execute: { type: 'ai-query', inputs: [
              { key: 'niche', label: 'Industry/niche', type: 'text', required: true },
              { key: 'geography', label: 'Geography', type: 'select', default: 'uk', options: [
                  { value: 'uk', label: 'UK' }, { value: 'europe', label: 'Europe' }, { value: 'global', label: 'Global' }] }
          ], buildPayload: function (i) { return { question: 'Estimate market size for the ' + i.niche + ' market in ' + i.geography + '.\n1. TOP-DOWN: Total market, serviceable market, addressable market (TAM/SAM/SOM)\n2. BOTTOM-UP: Player count x average revenue\n3. GROWTH: Historical CAGR, projected CAGR (5 years)\n4. KEY DRIVERS: What fuels growth\n5. KEY RISKS: What could slow growth\n6. SOURCES: Where this data comes from\n\nProvide ranges where exact figures are uncertain.' }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          blocks: [{id:'ai-analyse',role:'core'},{id:'web-fetch',role:'enhance'},{id:'companies-house-lookup',role:'enhance'},{id:'pdf-export',role:'output'}], requires: ['groq'], tags: ['market', 'sizing', 'tam', 'sam'] },

        { id: 'intel-deal-comps-tracker', name: 'M&A Deal Comps Tracker', icon: '&#128200;', category: 'intel',
          impact: 4, complexity: 'High', status: 'planned', timeSavedMin: 25, estimatedTime: '15-25s',
          description: 'Running log of comparable M&A transactions with multiples, buyers, and trends.',
          execute: { type: 'ai-query', inputs: [
              { key: 'sector', label: 'Sector', type: 'text', required: true },
              { key: 'size_range', label: 'Deal size range', type: 'text', placeholder: 'e.g. £5-50M' }
          ], buildPayload: function (i) { return { question: 'Compile recent M&A comparable transactions in ' + i.sector + ' sector' + (i.size_range ? ' (' + i.size_range + ' range)' : '') + '. For each: buyer, target, deal value, implied revenue multiple, EBITDA multiple, date. Then analyse trends in multiples over time.' }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          blocks: [{id:'ai-analyse',role:'core'},{id:'web-fetch',role:'enhance'},{id:'clipboard-copy',role:'output'}], requires: ['groq'], tags: ['deal-comps', 'multiples', 'tracker'] },

        { id: 'intel-talent-signal', name: 'Talent Signal Monitor', icon: '&#128101;', category: 'intel',
          impact: 3, complexity: 'Medium', status: 'planned', timeSavedMin: 15, estimatedTime: '10-15s',
          description: 'Track key hires, departures, and job postings as buying/selling signals at target companies.',
          execute: { type: 'ai-query', inputs: [
              { key: 'company', label: 'Company name', type: 'text', required: true }
          ], buildPayload: function (i) { return { question: 'Analyse talent signals for ' + i.company + ':\n1. Recent key hires (last 6 months)\n2. Recent departures\n3. Open positions (what roles are they hiring for?)\n4. Glassdoor/Indeed signals\n5. LinkedIn employee count trend\n6. INTERPRETATION: What do these signals suggest (growing, shrinking, pivoting, struggling)?' }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          blocks: [{id:'ai-analyse',role:'core'},{id:'linkedin-profile',role:'enhance'},{id:'web-fetch',role:'enhance'}], requires: ['groq'], tags: ['talent', 'signal', 'hiring', 'intelligence'] },

        { id: 'intel-regulatory-alert', name: 'Regulatory Alert', icon: '&#128220;', category: 'intel',
          impact: 3, complexity: 'Medium', status: 'planned', timeSavedMin: 15, estimatedTime: '10-15s',
          description: 'Monitor UK regulatory bodies for updates affecting portfolio or targets.',
          execute: { type: 'ai-query', inputs: [
              { key: 'sectors', label: 'Sectors to monitor', type: 'text', required: true, placeholder: 'e.g. E-commerce, Health supplements, CBD' }
          ], buildPayload: function (i) { return { question: 'Check for recent UK regulatory updates affecting ' + i.sectors + ' sectors from: FCA, CMA, ASA, MHRA, ICO. For each update: regulatory body, summary, effective date, impact assessment, and required actions for eComplete.' }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          blocks: [{id:'ai-analyse',role:'core'},{id:'web-fetch',role:'enhance'},{id:'notification',role:'output'}], requires: ['groq'], tags: ['regulatory', 'alert', 'compliance'] },

        { id: 'intel-brand-health-check', name: 'Brand Health Check', icon: '&#128153;', category: 'intel',
          impact: 3, complexity: 'Medium', status: 'ready', timeSavedMin: 20, estimatedTime: '10-20s',
          description: 'Brand health score: search visibility, review sentiment, social trajectory, mentions.',
          execute: { type: 'ai-query', inputs: [
              { key: 'brand', label: 'Brand/domain', type: 'text', required: true }
          ], buildPayload: function (i) { return { question: 'Conduct a brand health check for ' + i.brand + ':\n1. SEARCH VISIBILITY: Organic traffic estimate, trending keywords\n2. REVIEW SENTIMENT: Trustpilot/Google rating, recent review trend\n3. SOCIAL HEALTH: Follower growth, engagement rates, posting consistency\n4. MENTION FREQUENCY: How often is the brand being discussed\n5. OVERALL SCORE: Brand health 1-10 with justification\n6. RECOMMENDATIONS: Top 3 actions to improve brand health' }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          blocks: [{id:'ai-analyse',role:'core'},{id:'web-fetch',role:'enhance'},{id:'clipboard-copy',role:'output'}], requires: ['groq'], tags: ['brand', 'health', 'sentiment', 'social'] }
    ]);

    // ---- Category 9: Data & Systems (7 skills) ----
    window.SkillsRegistry.registerBatch([
        { id: 'data-full-pipeline-refresh', name: 'Full Pipeline Refresh', icon: '&#128260;', category: 'data',
          impact: 3, complexity: 'High', status: 'planned', timeSavedMin: 15, estimatedTime: '30-60s',
          description: 'Run full pipeline orchestrator: fetch all sources, analyse, sync to Supabase.',
          execute: { type: 'api-call', inputs: [], buildPayload: function () { return { target: 'supabase', action: 'full_refresh' }; }, resultType: 'json' },
          blocks: [{id:'data-read',role:'core'},{id:'hubspot-read',role:'enhance'},{id:'monday-read',role:'enhance'},{id:'data-store',role:'output'}], requires: ['supabase', 'hubspot', 'monday'], tags: ['refresh', 'pipeline', 'sync'] },

        { id: 'data-hubspot-cleanup', name: 'HubSpot Data Cleanup', icon: '&#129529;', category: 'data',
          impact: 4, complexity: 'Medium', status: 'ready', timeSavedMin: 30, estimatedTime: '10-20s',
          description: 'Identify duplicates, missing fields, contacts without email, orphaned companies.',
          execute: { type: 'ai-query', inputs: [],
            buildPayload: function () { return { question: 'Analyse our HubSpot CRM data quality. Identify: duplicate contacts (by name/email), contacts missing email, companies with no associated deals, deals with missing required fields (value, stage, owner), and contacts not contacted in 6+ months. Provide counts and recommended cleanup actions. Use dashboard data.' }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          blocks: [{id:'ai-analyse',role:'core'},{id:'hubspot-read',role:'enhance'}], requires: ['groq'], tags: ['hubspot', 'cleanup', 'data-quality'] },

        { id: 'data-contact-merge', name: 'Merge Duplicate Contacts', icon: '&#129309;', category: 'data',
          impact: 2, complexity: 'Low', status: 'planned', timeSavedMin: 10, estimatedTime: '3-5s',
          description: 'Merge two duplicate HubSpot contacts, preserving the richer record.',
          execute: { type: 'api-call', inputs: [
              { key: 'primary_id', label: 'Primary Contact ID (to keep)', type: 'text', required: true },
              { key: 'secondary_id', label: 'Secondary Contact ID (to merge)', type: 'text', required: true }
          ], buildPayload: function (i) { return { target: 'hubspot', path: '/crm/v3/objects/contacts/merge', method: 'POST', body: { primaryObjectId: i.primary_id, objectIdToMerge: i.secondary_id } }; },
            resultType: 'json' },
          blocks: [{id:'hubspot-write',role:'core'},{id:'hubspot-read',role:'core'}], requires: ['hubspot'], tags: ['merge', 'contact', 'duplicate'] },

        { id: 'data-monday-item-create', name: 'Create Monday Item', icon: '&#10133;', category: 'data',
          impact: 2, complexity: 'Low', status: 'planned', timeSavedMin: 5, estimatedTime: '3-5s',
          description: 'Create a new item on any Monday.com board with column values.',
          execute: { type: 'api-call', inputs: [
              { key: 'board', label: 'Board name or ID', type: 'text', required: true },
              { key: 'item_name', label: 'Item name', type: 'text', required: true },
              { key: 'status', label: 'Status', type: 'text', placeholder: 'e.g. Working on it' }
          ], buildPayload: function (i) { return { target: 'monday', action: 'create_item', board: i.board, name: i.item_name, status: i.status }; },
            resultType: 'json' },
          blocks: [{id:'monday-write',role:'core'}], requires: ['monday'], tags: ['monday', 'create', 'item'] },

        { id: 'data-monday-status-update', name: 'Update Monday Status', icon: '&#9998;', category: 'data',
          impact: 1, complexity: 'Low', status: 'planned', timeSavedMin: 3, estimatedTime: '2-3s',
          description: 'Quick status update on a Monday.com item.',
          execute: { type: 'api-call', inputs: [
              { key: 'item_id', label: 'Item ID', type: 'text', required: true },
              { key: 'status', label: 'New status', type: 'text', required: true }
          ], buildPayload: function (i) { return { target: 'monday', action: 'update_status', item_id: i.item_id, status: i.status }; },
            resultType: 'json' },
          blocks: [{id:'monday-write',role:'core'}], requires: ['monday'], tags: ['monday', 'status', 'update'] },

        { id: 'data-export-deal-pack', name: 'Export Deal Data Pack', icon: '&#128193;', category: 'data',
          impact: 3, complexity: 'Medium', status: 'ready', timeSavedMin: 15, estimatedTime: '10-15s',
          description: 'Export all deal data as structured summary: contacts, activities, CDD, NDA, financials.',
          execute: { type: 'ai-query', inputs: [
              { key: 'deal', label: 'Deal name', type: 'text', required: true },
              { key: 'data', label: 'All available deal data', type: 'textarea', required: true }
          ], buildPayload: function (i) { return { question: 'Format this deal data as a structured export pack for ' + i.deal + '.\nOrganise into sections: Deal Overview, Contacts, Activity Log, CDD Status, NDA Status, Financial Data, Outstanding Items, Risk Register.\n\nData: ' + i.data, report: true }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }, { label: '&#128424; Export', handler: 'exportPdf' }] },
          blocks: [{id:'ai-analyse',role:'core'},{id:'hubspot-read',role:'enhance'},{id:'dashboard-context',role:'enhance'},{id:'pdf-export',role:'output'}], requires: ['groq'], tags: ['export', 'deal', 'data-pack'] },

        { id: 'data-snapshot-diff', name: 'Data Change Report', icon: '&#128270;', category: 'data',
          impact: 2, complexity: 'Medium', status: 'ready', timeSavedMin: 10, estimatedTime: '8-12s',
          description: 'Compare data snapshots: new contacts, stage changes, value changes since last check.',
          execute: { type: 'ai-query', inputs: [
              { key: 'source', label: 'Data source', type: 'select', default: 'hubspot', options: [
                  { value: 'hubspot', label: 'HubSpot CRM' }, { value: 'monday', label: 'Monday.com' }, { value: 'both', label: 'Both' }] },
              { key: 'period', label: 'Since when', type: 'select', default: 'yesterday', options: [
                  { value: 'yesterday', label: 'Yesterday' }, { value: 'last_week', label: 'Last week' }, { value: 'last_month', label: 'Last month' }] }
          ], buildPayload: function (i) { return { question: 'Generate a data change report for ' + i.source + ' since ' + i.period + '. Include: new records added, records modified, stage/status changes, value changes, deleted/archived items. Highlight significant changes that need attention. Use dashboard data.' }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          blocks: [{id:'ai-analyse',role:'core'},{id:'data-read',role:'enhance'}], requires: ['groq'], tags: ['snapshot', 'diff', 'changes', 'data'] }
    ]);

    // ---- Category 10: Portfolio & E-Commerce (5 skills) ----
    window.SkillsRegistry.registerBatch([
        { id: 'ecom-seo-performance', name: 'SEO Performance Report', icon: '&#128200;', category: 'portfolio',
          impact: 4, complexity: 'Medium', status: 'ready', timeSavedMin: 20, estimatedTime: '10-20s',
          description: 'Top pages, keyword rankings, CTR trends, organic traffic changes, quick win recommendations.',
          execute: { type: 'ai-query', inputs: [
              { key: 'domain', label: 'Domain', type: 'text', required: true, placeholder: 'e.g. naturecan.com' },
              { key: 'period', label: 'Period', type: 'select', default: '30d', options: [
                  { value: '7d', label: 'Last 7 days' }, { value: '30d', label: 'Last 30 days' }, { value: '90d', label: 'Last 90 days' }] }
          ], buildPayload: function (i) { return { question: 'Generate an SEO performance report for ' + i.domain + ' (' + i.period + '):\n1. TOP PAGES by organic traffic\n2. KEYWORD RANKINGS: Movement (up/down/new)\n3. CTR TRENDS: Average CTR, best/worst performing\n4. TRAFFIC CHANGES: Organic session trends\n5. QUICK WINS: Top 5 SEO improvements to implement now\n6. COMPETITOR COMPARISON: How we compare to top organic competitors' }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          blocks: [{id:'ai-analyse',role:'core'},{id:'web-fetch',role:'enhance'},{id:'dashboard-context',role:'enhance'},{id:'clipboard-copy',role:'output'}], requires: ['groq'], tags: ['seo', 'performance', 'organic', 'traffic'] },

        { id: 'ecom-brand-competitor-scan', name: 'Brand Competitor Scan', icon: '&#127919;', category: 'portfolio',
          impact: 4, complexity: 'Medium', status: 'ready', timeSavedMin: 25, estimatedTime: '15-25s',
          description: 'Comparative analysis: product range, pricing, social following, SEO, ad spend signals.',
          execute: { type: 'ai-query', inputs: [
              { key: 'brand', label: 'Our brand', type: 'text', required: true },
              { key: 'competitors', label: 'Competitor brands/domains', type: 'textarea', required: true, placeholder: 'One per line' }
          ], buildPayload: function (i) { return { question: 'Conduct a brand competitive scan for ' + i.brand + ' vs competitors:\n' + i.competitors + '\n\nCompare: product range breadth, pricing positioning, social media following + engagement, SEO visibility, ad spend signals, unique selling points, customer sentiment. Create a comparison matrix and identify where ' + i.brand + ' can win.' }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          blocks: [{id:'ai-analyse',role:'core'},{id:'web-fetch',role:'enhance'},{id:'clipboard-copy',role:'output'}], requires: ['groq'], tags: ['brand', 'competitor', 'scan', 'ecommerce'] },

        { id: 'ecom-social-audit', name: 'Social Media Audit', icon: '&#128241;', category: 'portfolio',
          impact: 3, complexity: 'Medium', status: 'ready', timeSavedMin: 20, estimatedTime: '10-20s',
          description: 'Cross-platform analysis: followers, engagement, posting frequency, content themes.',
          execute: { type: 'ai-query', inputs: [
              { key: 'brand', label: 'Brand name', type: 'text', required: true },
              { key: 'handles', label: 'Social handles (optional)', type: 'textarea', placeholder: 'IG: @brand\nTT: @brand\nLI: company/brand' }
          ], buildPayload: function (i) { return { question: 'Conduct a social media audit for ' + i.brand + (i.handles ? '. Handles: ' + i.handles : '') + '.\nAnalyse across Instagram, TikTok, LinkedIn, Twitter/X, Facebook:\n1. Follower counts and growth trajectory\n2. Engagement rates\n3. Posting frequency\n4. Content themes and what performs best\n5. Audience demographics estimate\n6. RECOMMENDATIONS: Top 5 actions to improve social performance' }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          blocks: [{id:'ai-analyse',role:'core'},{id:'web-fetch',role:'enhance'},{id:'clipboard-copy',role:'output'}], requires: ['groq'], tags: ['social', 'audit', 'instagram', 'tiktok'] },

        { id: 'ecom-product-launch-tracker', name: 'Product Launch Tracker', icon: '&#128230;', category: 'portfolio',
          impact: 3, complexity: 'Medium', status: 'planned', timeSavedMin: 15, estimatedTime: '10-15s',
          description: 'Monitor competitor product pages for new launches, price changes, discontinued items.',
          execute: { type: 'api-call', inputs: [
              { key: 'domains', label: 'Competitor domains to monitor', type: 'textarea', required: true }
          ], buildPayload: function (i) { return { target: 'web-scraper', action: 'monitor_products', domains: i.domains.split('\n').map(function(s){return s.trim();}) }; },
            resultType: 'json' },
          blocks: [{id:'web-fetch',role:'core'},{id:'ai-analyse',role:'enhance'},{id:'notification',role:'output'}], requires: ['web-scraper'], tags: ['product', 'launch', 'monitor', 'competitor'] },

        { id: 'ecom-market-opportunity', name: 'Market Opportunity Scanner', icon: '&#128301;', category: 'portfolio',
          impact: 4, complexity: 'High', status: 'ready', timeSavedMin: 40, estimatedTime: '20-35s',
          description: 'AI identifies underserved market segments: search volume vs competition, trending categories, targets.',
          execute: { type: 'ai-query', inputs: [
              { key: 'category', label: 'E-commerce category/niche', type: 'text', required: true, placeholder: 'e.g. Health supplements, CBD products, Sustainable fashion' },
              { key: 'focus', label: 'Opportunity focus', type: 'select', default: 'gaps', options: [
                  { value: 'gaps', label: 'Market gaps' }, { value: 'trending', label: 'Trending categories' },
                  { value: 'acquisition', label: 'Acquisition targets' }] }
          ], buildPayload: function (i) { return { question: 'Scan for ' + i.focus + ' in the ' + i.category + ' e-commerce space.\n1. UNDERSERVED SEGMENTS: High search volume but low competition\n2. TRENDING SUB-CATEGORIES: What is growing fastest\n3. PRICING GAPS: Where is there room for disruption\n4. GEOGRAPHIC OPPORTUNITIES: Markets with demand but few players\n5. ACQUISITION TARGETS: Brands that could be acquired to capture these opportunities\n6. RECOMMENDED STRATEGY: How eComplete should approach these opportunities' }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }, { label: '&#128424; Export', handler: 'exportPdf' }] },
          blocks: [{id:'ai-analyse',role:'core'},{id:'web-fetch',role:'enhance'},{id:'companies-house-lookup',role:'enhance'},{id:'pdf-export',role:'output'}], requires: ['groq'], tags: ['opportunity', 'market', 'ecommerce', 'scanner'] }
    ]);
})();
