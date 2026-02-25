/* ============================================================
   Skills — Commercial Due Diligence (12 skills)
   ============================================================ */
(function () {
    'use strict';

    window.SkillsRegistry.registerBatch([
        { id: 'cdd-market-research', name: 'CDD Market Research', icon: '&#127760;', category: 'cdd',
          impact: 5, complexity: 'Medium', status: 'ready', timeSavedMin: 90, estimatedTime: '20-40s',
          description: 'AI-generated market size/growth analysis, competitive landscape, addressable market, and trend assessment.',
          execute: { type: 'ai-query', inputs: [
              { key: 'company', label: 'Target company name', type: 'text', required: true },
              { key: 'industry', label: 'Industry/sector', type: 'text', required: true, placeholder: 'e.g. E-commerce, SaaS, Health & Wellness' },
              { key: 'geography', label: 'Geography', type: 'select', default: 'uk', options: [
                  { value: 'uk', label: 'United Kingdom' }, { value: 'europe', label: 'Europe' },
                  { value: 'global', label: 'Global' }, { value: 'us', label: 'United States' }] }
          ], buildPayload: function (i) { return { question: 'Conduct comprehensive market research for CDD purposes on ' + i.company + ' in the ' + i.industry + ' sector (' + i.geography + ' market). Include:\n1. MARKET SIZE: TAM, SAM, SOM estimates with sources\n2. MARKET GROWTH: Historical and projected CAGR\n3. KEY DRIVERS: What is driving growth\n4. COMPETITIVE LANDSCAPE: Major players, market shares, positioning\n5. BARRIERS TO ENTRY: What protects incumbents\n6. TRENDS: Key trends affecting the sector (tech, regulatory, consumer)\n7. RISKS: Market-level risks and threats\n8. OPPORTUNITY ASSESSMENT: Where is the white space for growth', report: true }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }, { label: '&#128424; Export', handler: 'exportPdf' }] },
          requires: ['groq'], tags: ['cdd', 'market', 'research', 'analysis'] },

        { id: 'cdd-competitor-analysis', name: 'Competitor Analysis', icon: '&#127942;', category: 'cdd',
          impact: 5, complexity: 'Medium', status: 'ready', timeSavedMin: 60, estimatedTime: '20-35s',
          description: 'AI competitor matrix: revenue estimates, market share, digital presence, SWOT comparison.',
          execute: { type: 'ai-query', inputs: [
              { key: 'company', label: 'Target company', type: 'text', required: true },
              { key: 'competitors', label: 'Known competitors (optional)', type: 'textarea', placeholder: 'One per line, or leave blank for AI to identify' }
          ], buildPayload: function (i) { return { question: 'Conduct a competitive analysis for CDD on ' + i.company + '. ' + (i.competitors ? 'Known competitors: ' + i.competitors + '. Also identify any we\'ve missed.' : 'Identify the top 5-8 competitors.') + '\nFor each competitor, provide:\n- Company name & HQ\n- Estimated revenue range\n- Market share estimate\n- Key differentiators\n- Digital presence strength (1-10)\n- Strengths and weaknesses\n\nThen provide a SWOT analysis for ' + i.company + ' relative to the competitive landscape.', report: true }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }, { label: '&#128424; Export', handler: 'exportPdf' }] },
          requires: ['groq'], tags: ['cdd', 'competitor', 'swot', 'analysis'] },

        { id: 'cdd-financial-snapshot', name: 'Financial Snapshot', icon: '&#163;', category: 'cdd',
          impact: 4, complexity: 'Low', status: 'ready', timeSavedMin: 30, estimatedTime: '10-20s',
          description: 'Pull Companies House data: revenue, profit, assets, directors, PSC, filing history.',
          execute: { type: 'ai-query', inputs: [
              { key: 'company', label: 'Company name or CH number', type: 'text', required: true }
          ], buildPayload: function (i) { return { question: 'Provide a financial snapshot for ' + i.company + ' using Companies House public data. Include:\n1. COMPANY INFO: Registration number, incorporation date, registered address, SIC codes\n2. DIRECTORS: Current directors with appointment dates\n3. PSC: Persons with significant control\n4. FINANCIALS: Latest filed accounts - revenue, profit/loss, total assets, net assets, cash\n5. FILING HISTORY: Last 5 filings with dates\n6. CHARGES: Any outstanding charges\n7. RED FLAGS: Late filings, director changes, adverse indicators', report: true }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }, { label: '&#128424; Export', handler: 'exportPdf' }] },
          requires: ['groq'], tags: ['cdd', 'financial', 'companies-house'] },

        { id: 'cdd-digital-presence-audit', name: 'Digital Presence Audit', icon: '&#128187;', category: 'cdd',
          impact: 4, complexity: 'Medium', status: 'ready', timeSavedMin: 45, estimatedTime: '15-25s',
          description: 'SEO visibility, social following, ad spend signals, tech stack detection for a target company.',
          execute: { type: 'ai-query', inputs: [
              { key: 'domain', label: 'Company domain', type: 'text', required: true, placeholder: 'e.g. acme.com' }
          ], buildPayload: function (i) { return { question: 'Conduct a digital presence audit for ' + i.domain + '. Assess:\n1. SEO: Estimated organic traffic, top ranking keywords, domain authority estimate\n2. SOCIAL MEDIA: Followers across platforms, engagement rates, posting frequency\n3. PAID ADVERTISING: Any visible ad spend signals (Google Ads, Meta Ads)\n4. TECH STACK: CMS, e-commerce platform, analytics tools, marketing automation\n5. CONTENT: Blog frequency, content quality, lead magnets\n6. REVIEWS: Trustpilot/Google rating, review volume\n7. OVERALL SCORE: Digital maturity score (1-10) with justification', report: true }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }, { label: '&#128424; Export', handler: 'exportPdf' }] },
          requires: ['groq'], tags: ['cdd', 'digital', 'seo', 'social'] },

        { id: 'cdd-customer-sentiment', name: 'Customer Sentiment', icon: '&#128172;', category: 'cdd',
          impact: 4, complexity: 'Medium', status: 'ready', timeSavedMin: 40, estimatedTime: '15-25s',
          description: 'Analyse reviews, social sentiment, common complaints, and estimate NPS for a target.',
          execute: { type: 'ai-query', inputs: [
              { key: 'company', label: 'Company/brand name', type: 'text', required: true }
          ], buildPayload: function (i) { return { question: 'Analyse customer sentiment for ' + i.company + '. Include:\n1. REVIEW PLATFORMS: Trustpilot rating, Google reviews, app store ratings\n2. SENTIMENT BREAKDOWN: Positive/neutral/negative percentages\n3. COMMON PRAISE: Top 5 things customers love\n4. COMMON COMPLAINTS: Top 5 issues raised\n5. NPS ESTIMATE: Based on available data\n6. SOCIAL SENTIMENT: Overall brand perception on social media\n7. RISK ASSESSMENT: Any reputational risks or trending negative issues', report: true }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          requires: ['groq'], tags: ['cdd', 'sentiment', 'reviews', 'nps'] },

        { id: 'cdd-executive-summary', name: 'Generate CDD Summary', icon: '&#128196;', category: 'cdd',
          impact: 5, complexity: 'High', status: 'ready', timeSavedMin: 60, estimatedTime: '25-45s',
          description: 'AI generates a 2-3 page executive CDD summary: investment thesis, risks, growth levers, valuation range.',
          execute: { type: 'ai-query', inputs: [
              { key: 'company', label: 'Company name', type: 'text', required: true },
              { key: 'data', label: 'All CDD data gathered (paste summaries)', type: 'textarea', required: true, placeholder: 'Paste market research, financial data, competitor analysis, digital audit results...' },
              { key: 'deal_value', label: 'Indicative deal value (optional)', type: 'text', placeholder: 'e.g. £5-8M' }
          ], buildPayload: function (i) { return { question: 'Generate a comprehensive CDD Executive Summary for ' + i.company + (i.deal_value ? ' (indicative value: ' + i.deal_value + ')' : '') + '. Structure as:\n1. EXECUTIVE OVERVIEW (2-3 paragraphs)\n2. INVESTMENT THESIS: Why this is compelling\n3. KEY METRICS: Revenue, growth, profitability, market position\n4. COMPETITIVE POSITIONING: Where they sit vs competitors\n5. GROWTH LEVERS: 3-5 actionable growth opportunities\n6. KEY RISKS: Top 5 risks with mitigation strategies\n7. VALUATION CONTEXT: Comparable transaction multiples, indicative range\n8. RECOMMENDATION: Go/No-Go with conditions\n\nData gathered:\n' + i.data, report: true }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }, { label: '&#128424; Export', handler: 'exportPdf' }] },
          requires: ['groq'], tags: ['cdd', 'summary', 'executive', 'report'] },

        { id: 'cdd-full-pack', name: 'Run Full CDD Pack', icon: '&#128640;', category: 'cdd',
          impact: 5, complexity: 'High', status: 'ready', timeSavedMin: 180, estimatedTime: '2-5m',
          description: 'Runs all CDD skills sequentially: market, competitor, financial, digital, sentiment, then generates summary.',
          execute: { type: 'ai-query', inputs: [
              { key: 'company', label: 'Target company', type: 'text', required: true },
              { key: 'industry', label: 'Industry', type: 'text', required: true },
              { key: 'domain', label: 'Website domain', type: 'text', placeholder: 'e.g. acme.com' }
          ], buildPayload: function (i) { return { question: 'Conduct a FULL Commercial Due Diligence pack for ' + i.company + ' (' + i.industry + ', ' + (i.domain || 'domain unknown') + '). This is a comprehensive analysis covering ALL of the following:\n\n1. MARKET RESEARCH: TAM/SAM/SOM, growth rates, key drivers, trends\n2. COMPETITIVE ANALYSIS: Top competitors, market shares, SWOT\n3. FINANCIAL SNAPSHOT: Revenue estimates, profitability indicators, growth trajectory\n4. DIGITAL PRESENCE: SEO, social, tech stack, content maturity\n5. CUSTOMER SENTIMENT: Reviews, NPS estimate, brand perception\n6. MANAGEMENT TEAM: Key people, backgrounds, tenure, strengths\n7. RISK REGISTER: Commercial, market, operational, regulatory risks\n8. GROWTH OPPORTUNITIES: Organic and inorganic growth levers\n9. VALUATION CONTEXT: Comparable multiples and indicative range\n10. EXECUTIVE SUMMARY: Go/No-Go recommendation\n\nMake this boardroom-ready.', report: true }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }, { label: '&#128424; Export', handler: 'exportPdf' }] },
          requires: ['groq'], tags: ['cdd', 'full', 'pack', 'comprehensive'] },

        { id: 'companies-house-filing-alert', name: 'Filing Alert', icon: '&#128276;', category: 'cdd',
          impact: 3, complexity: 'Medium', status: 'planned', timeSavedMin: 15, estimatedTime: '5-10s',
          description: 'Check Companies House for new filings on watched companies.',
          execute: { type: 'api-call', inputs: [
              { key: 'companies', label: 'Company numbers (comma-separated)', type: 'text', required: true }
          ], buildPayload: function (i) { return { target: 'companies-house', action: 'check_filings', companies: i.companies.split(',').map(function(s){return s.trim();}) }; },
            resultType: 'json' },
          requires: ['companies-house'], tags: ['filing', 'alert', 'companies-house'] },

        { id: 'cdd-revenue-triangulation', name: 'Revenue Triangulation', icon: '&#128208;', category: 'cdd',
          impact: 4, complexity: 'Medium', status: 'ready', timeSavedMin: 30, estimatedTime: '15-25s',
          description: 'Cross-reference filed accounts, employee count, and digital signals to estimate current revenue.',
          execute: { type: 'ai-query', inputs: [
              { key: 'company', label: 'Company name', type: 'text', required: true },
              { key: 'known_data', label: 'Any known data points', type: 'textarea', placeholder: 'e.g. Filed accounts show £3.2M (2023), LinkedIn shows 45 employees, domain gets ~50K monthly visits' }
          ], buildPayload: function (i) { return { question: 'Triangulate the current revenue for ' + i.company + ' using multiple data sources. Methods:\n1. ACCOUNTS-BASED: Latest filed accounts, growth trajectory\n2. EMPLOYEE-BASED: Employee count x revenue per employee (industry benchmark)\n3. DIGITAL-BASED: Web traffic x conversion rate x AOV estimates\n4. BENCHMARK: Industry peer comparisons\n\nKnown data: ' + (i.known_data || 'Use publicly available information') + '\n\nProvide a revenue range estimate with confidence level and methodology notes.', report: true }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          requires: ['groq'], tags: ['revenue', 'triangulation', 'estimate'] },

        { id: 'cdd-management-team-review', name: 'Management Team Review', icon: '&#128101;', category: 'cdd',
          impact: 4, complexity: 'Medium', status: 'ready', timeSavedMin: 30, estimatedTime: '15-25s',
          description: 'Profile key management: backgrounds, tenure, strengths, red flags, team score.',
          execute: { type: 'ai-query', inputs: [
              { key: 'company', label: 'Company name', type: 'text', required: true },
              { key: 'known_team', label: 'Known team members (optional)', type: 'textarea', placeholder: 'CEO: John Smith\nCFO: Sarah Jones' }
          ], buildPayload: function (i) { return { question: 'Review the management team of ' + i.company + ' for CDD purposes. ' + (i.known_team ? 'Known team: ' + i.known_team + '. ' : '') + 'For each key person:\n1. Name, title, approximate tenure\n2. Background summary (education, prior roles)\n3. LinkedIn activity level (active/moderate/inactive)\n4. Strengths for this role\n5. Any red flags (frequent job changes, gaps, controversies)\n\nOverall: Team depth score (1-10), key person dependency risk, succession readiness.', report: true }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          requires: ['groq'], tags: ['management', 'team', 'review', 'people'] },

        { id: 'cdd-risk-register', name: 'CDD Risk Register', icon: '&#9888;', category: 'cdd',
          impact: 4, complexity: 'Medium', status: 'ready', timeSavedMin: 25, estimatedTime: '15-20s',
          description: 'Auto-generate a risk register from CDD data: category, likelihood, impact, mitigation.',
          execute: { type: 'ai-query', inputs: [
              { key: 'company', label: 'Company name', type: 'text', required: true },
              { key: 'cdd_data', label: 'CDD findings to assess', type: 'textarea', required: true, placeholder: 'Paste key findings from market research, financials, digital audit...' }
          ], buildPayload: function (i) { return { question: 'Generate a comprehensive CDD Risk Register for ' + i.company + '. For each risk:\n- RISK ID (R001, R002...)\n- CATEGORY: Commercial / Financial / Operational / Market / Regulatory / Reputational\n- DESCRIPTION: What could go wrong\n- LIKELIHOOD: Low / Medium / High\n- IMPACT: Low / Medium / High / Critical\n- RISK SCORE: (likelihood x impact)\n- MITIGATION: Recommended action\n- OWNER: Who should manage this\n\nBase this on the following CDD data:\n' + i.cdd_data, report: true }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }, { label: '&#128424; Export', handler: 'exportPdf' }] },
          requires: ['groq'], tags: ['risk', 'register', 'cdd', 'assessment'] },

        { id: 'cdd-comparable-valuations', name: 'Comparable Valuations', icon: '&#128200;', category: 'cdd',
          impact: 4, complexity: 'High', status: 'ready', timeSavedMin: 45, estimatedTime: '20-35s',
          description: 'Pull recent comparable M&A transactions and public company multiples for valuation range.',
          execute: { type: 'ai-query', inputs: [
              { key: 'industry', label: 'Industry/sector', type: 'text', required: true },
              { key: 'revenue', label: 'Target revenue range', type: 'text', required: true, placeholder: 'e.g. £3-5M' },
              { key: 'geography', label: 'Geography', type: 'select', default: 'uk', options: [
                  { value: 'uk', label: 'UK' }, { value: 'europe', label: 'Europe' }, { value: 'global', label: 'Global' }] }
          ], buildPayload: function (i) { return { question: 'Provide comparable valuation analysis for a ' + i.industry + ' company with ' + i.revenue + ' revenue in ' + i.geography + '. Include:\n1. RECENT M&A TRANSACTIONS: 5-10 comparable deals with buyer, target, deal value, and implied multiples (EV/Revenue, EV/EBITDA)\n2. PUBLIC COMPANY MULTIPLES: Relevant listed companies with current trading multiples\n3. VALUATION RANGE: Implied valuation range based on comps\n4. PREMIUM/DISCOUNT FACTORS: What could command a premium or discount\n5. RECOMMENDED RANGE: Indicative offer range with justification', report: true }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }, { label: '&#128424; Export', handler: 'exportPdf' }] },
          requires: ['groq'], tags: ['valuation', 'comparable', 'multiples', 'ma'] }
    ]);
})();
