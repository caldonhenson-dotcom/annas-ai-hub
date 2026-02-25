/* ============================================================
   Skills — Deal Sourcing & Outreach (14 skills)
   ============================================================ */
(function () {
    'use strict';

    var P = '&#128269;'; // default prompt prefix for readability

    window.SkillsRegistry.registerBatch([
        { id: 'linkedin-prospect-research', name: 'Research Prospect', icon: '&#128270;', category: 'deal-sourcing',
          impact: 5, complexity: 'Low', status: 'ready', timeSavedMin: 45, estimatedTime: '15-30s',
          description: 'AI-powered deep research on any prospect: company overview, key people, pain points, opportunity assessment.',
          execute: { type: 'ai-query', inputs: [
              { key: 'target', label: 'Company or person name', type: 'text', required: true, placeholder: 'e.g. Acme Ltd or John Smith, CEO' },
              { key: 'context', label: 'Additional context (optional)', type: 'textarea', placeholder: 'e.g. looking at acquisition, interested in their SaaS division' }
          ], buildPayload: function (i) { return { question: 'Research this prospect thoroughly: ' + i.target + '. ' + (i.context || '') + ' Provide: company overview, key people with titles, estimated revenue, pain points, competitive landscape, conversation starters, and opportunity assessment for eComplete (M&A advisory).', report: true }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }, { label: '&#128424; Export', handler: 'exportPdf' }] },
          requires: ['groq'],
          blocks: [
              { id: 'ai-analyse', role: 'core' }, { id: 'web-fetch', role: 'enhance' },
              { id: 'companies-house-lookup', role: 'enhance' }, { id: 'hubspot-read', role: 'enhance' },
              { id: 'dashboard-context', role: 'enhance' }, { id: 'clipboard-copy', role: 'output' }, { id: 'pdf-export', role: 'output' }
          ],
          features: [
              { id: 'web-scraping', label: 'Live website scraping', block: 'web-fetch', default: true },
              { id: 'ch-data', label: 'Companies House data', block: 'companies-house-lookup', default: true },
              { id: 'crm-cross-ref', label: 'CRM cross-reference', block: 'hubspot-read', default: false }
          ],
          tags: ['linkedin', 'research', 'prospect', 'outreach'] },

        { id: 'linkedin-send-connection', name: 'Send Connection Request', icon: '&#129309;', category: 'deal-sourcing',
          impact: 2, complexity: 'Low', status: 'planned', timeSavedMin: 5, estimatedTime: '3-5s',
          description: 'Send personalised LinkedIn connection request to a prospect.',
          execute: { type: 'api-call', inputs: [
              { key: 'linkedin_url', label: 'LinkedIn Profile URL', type: 'text', required: true },
              { key: 'note', label: 'Personal note (optional)', type: 'textarea', placeholder: 'Max 300 chars' }
          ], buildPayload: function (i) { return { target: 'linkedin', action: 'connect', url: i.linkedin_url, note: i.note }; },
            resultType: 'json' },
          requires: ['linkedin'],
          blocks: [{ id: 'linkedin-message', role: 'core' }],
          tags: ['linkedin', 'connection', 'outreach'] },

        { id: 'linkedin-draft-outreach', name: 'Draft Outreach Message', icon: '&#128221;', category: 'deal-sourcing',
          impact: 4, complexity: 'Low', status: 'ready', timeSavedMin: 20, estimatedTime: '10-15s',
          description: 'AI drafts a personalised outreach message tailored to the prospect and sequence step.',
          execute: { type: 'ai-query', inputs: [
              { key: 'prospect', label: 'Prospect name & company', type: 'text', required: true },
              { key: 'step', label: 'Sequence step', type: 'select', default: '1', options: [
                  { value: '1', label: 'Step 1: Introduction' }, { value: '2', label: 'Step 2: Value-add follow-up' },
                  { value: '3', label: 'Step 3: Social proof' }, { value: '4', label: 'Step 4: Soft close' }] },
              { key: 'angle', label: 'Approach angle', type: 'text', placeholder: 'e.g. M&A advisory, partnership' }
          ], buildPayload: function (i) { return { question: 'Draft a LinkedIn outreach message (step ' + i.step + ') for ' + i.prospect + '. Angle: ' + (i.angle || 'M&A advisory') + '. Keep it 50-120 words, personal, no hard sell. eComplete is an M&A advisory firm helping mid-market companies with acquisitions and exits.' }; },
            resultType: 'draft', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          requires: ['groq'],
          blocks: [
              { id: 'ai-draft', role: 'core' }, { id: 'linkedin-profile', role: 'enhance' },
              { id: 'dashboard-context', role: 'enhance' }, { id: 'clipboard-copy', role: 'output' }
          ],
          tags: ['linkedin', 'outreach', 'message', 'draft'] },

        { id: 'linkedin-batch-enroll', name: 'Enroll in Sequence', icon: '&#128260;', category: 'deal-sourcing',
          impact: 4, complexity: 'Medium', status: 'planned', timeSavedMin: 30, estimatedTime: '5-10s',
          description: 'Enroll multiple prospects into an automated multi-step outreach sequence.',
          execute: { type: 'api-call', inputs: [
              { key: 'prospects', label: 'Prospect IDs (comma-separated)', type: 'text', required: true },
              { key: 'sequence', label: 'Sequence type', type: 'select', default: 'ma-intro', options: [
                  { value: 'ma-intro', label: 'M&A Introduction' }, { value: 'partnership', label: 'Partnership' },
                  { value: 'portfolio', label: 'Portfolio Opportunity' }] }
          ], buildPayload: function (i) { return { target: 'supabase', action: 'enroll', prospects: i.prospects.split(','), sequence: i.sequence }; },
            resultType: 'json' },
          requires: ['supabase'],
          blocks: [
              { id: 'data-store', role: 'core' }, { id: 'linkedin-message', role: 'enhance' },
              { id: 'notification', role: 'output' }
          ],
          tags: ['outreach', 'sequence', 'automation'] },

        { id: 'linkedin-reply-classifier', name: 'Classify Inbound Reply', icon: '&#127991;', category: 'deal-sourcing',
          impact: 3, complexity: 'Low', status: 'ready', timeSavedMin: 10, estimatedTime: '5-8s',
          description: 'AI classifies an inbound reply: interested, not now, question, objection, or unsubscribe.',
          execute: { type: 'ai-query', inputs: [
              { key: 'message', label: 'Paste the inbound message', type: 'textarea', required: true }
          ], buildPayload: function (i) { return { question: 'Classify this inbound reply from a prospect. Categories: INTERESTED, NOT_NOW, QUESTION, OBJECTION, UNSUBSCRIBE. Also provide: sentiment (positive/neutral/negative), key intent, and suggested next action. Message: "' + i.message + '"' }; },
            resultType: 'markdown' },
          requires: ['groq'],
          blocks: [{ id: 'ai-analyse', role: 'core' }, { id: 'dashboard-context', role: 'enhance' }],
          tags: ['classify', 'inbound', 'reply', 'intent'] },

        { id: 'linkedin-auto-reply', name: 'Draft Reply to Prospect', icon: '&#128172;', category: 'deal-sourcing',
          impact: 3, complexity: 'Low', status: 'ready', timeSavedMin: 15, estimatedTime: '8-12s',
          description: 'AI drafts a contextual reply based on the conversation history and classified intent.',
          execute: { type: 'ai-query', inputs: [
              { key: 'their_msg', label: 'Their latest message', type: 'textarea', required: true },
              { key: 'intent', label: 'Classified intent', type: 'select', default: 'interested', options: [
                  { value: 'interested', label: 'Interested' }, { value: 'question', label: 'Question' },
                  { value: 'objection', label: 'Objection' }, { value: 'not_now', label: 'Not Now' }] }
          ], buildPayload: function (i) { return { question: 'Draft a reply to this prospect message (intent: ' + i.intent + '). Be helpful, professional, concise (50-100 words). eComplete is an M&A advisory firm. Their message: "' + i.their_msg + '"' }; },
            resultType: 'draft', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          requires: ['groq'],
          blocks: [
              { id: 'ai-draft', role: 'core' }, { id: 'dashboard-context', role: 'enhance' },
              { id: 'clipboard-copy', role: 'output' }
          ],
          tags: ['reply', 'draft', 'conversation'] },

        { id: 'linkedin-conversation-sync', name: 'Sync LinkedIn Inbox', icon: '&#128229;', category: 'deal-sourcing',
          impact: 3, complexity: 'Medium', status: 'planned', timeSavedMin: 10, estimatedTime: '10-20s',
          description: 'Sync all recent LinkedIn conversations to Supabase and flag new inbound messages.',
          execute: { type: 'api-call', inputs: [], buildPayload: function () { return { target: 'linkedin', action: 'sync_inbox' }; }, resultType: 'json' },
          requires: ['linkedin', 'supabase'],
          blocks: [{ id: 'linkedin-profile', role: 'core' }, { id: 'data-store', role: 'core' }, { id: 'notification', role: 'output' }],
          tags: ['linkedin', 'sync', 'inbox'] },

        { id: 'hubspot-import-prospect', name: 'Import Prospect to CRM', icon: '&#10133;', category: 'deal-sourcing',
          impact: 3, complexity: 'Low', status: 'planned', timeSavedMin: 8, estimatedTime: '3-5s',
          description: 'Create a new HubSpot contact from prospect data with company association.',
          execute: { type: 'api-call', inputs: [
              { key: 'name', label: 'Full name', type: 'text', required: true },
              { key: 'email', label: 'Email', type: 'text', required: true },
              { key: 'company', label: 'Company', type: 'text' },
              { key: 'title', label: 'Job title', type: 'text' }
          ], buildPayload: function (i) { return { target: 'hubspot', path: '/crm/v3/objects/contacts', method: 'POST', body: { properties: { firstname: i.name.split(' ')[0], lastname: i.name.split(' ').slice(1).join(' '), email: i.email, company: i.company, jobtitle: i.title } } }; },
            resultType: 'json' },
          requires: ['hubspot'],
          blocks: [{ id: 'hubspot-write', role: 'core' }, { id: 'linkedin-profile', role: 'enhance' }],
          tags: ['hubspot', 'contact', 'import', 'crm'] },

        { id: 'lead-score-recalculate', name: 'Recalculate Lead Scores', icon: '&#128202;', category: 'deal-sourcing',
          impact: 4, complexity: 'Medium', status: 'planned', timeSavedMin: 15, estimatedTime: '15-30s',
          description: 'Recalculate AI lead scores for all prospects based on fit and engagement signals.',
          execute: { type: 'api-call', inputs: [], buildPayload: function () { return { target: 'supabase', action: 'recalculate_scores' }; }, resultType: 'json' },
          requires: ['supabase', 'groq'],
          blocks: [
              { id: 'ai-analyse', role: 'core' }, { id: 'data-store', role: 'core' },
              { id: 'hubspot-read', role: 'enhance' }, { id: 'notification', role: 'output' }
          ],
          tags: ['scoring', 'leads', 'ai'] },

        { id: 'batch-prospect-research', name: 'Batch Research (20)', icon: '&#128218;', category: 'deal-sourcing',
          impact: 5, complexity: 'High', status: 'ready', timeSavedMin: 120, estimatedTime: '2-5m',
          description: 'Run deep AI research on up to 20 prospects in one batch. Generates individual briefs for each.',
          execute: { type: 'ai-query', inputs: [
              { key: 'prospects', label: 'Company names (one per line)', type: 'textarea', required: true, placeholder: 'Acme Ltd\nGlobex Corp\nInitech Solutions' }
          ], buildPayload: function (i) { return { question: 'Research each of these companies for M&A opportunity assessment. For each, provide: brief overview (2-3 lines), estimated revenue range, sector, key people, digital presence strength (1-10), and acquisition fit score (1-10) for eComplete. Companies:\n' + i.prospects, report: true }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }, { label: '&#128424; Export', handler: 'exportPdf' }] },
          requires: ['groq'],
          blocks: [
              { id: 'ai-analyse', role: 'core' }, { id: 'web-fetch', role: 'enhance' },
              { id: 'companies-house-lookup', role: 'enhance' }, { id: 'hubspot-read', role: 'enhance' },
              { id: 'clipboard-copy', role: 'output' }, { id: 'pdf-export', role: 'output' }
          ],
          features: [
              { id: 'web-scraping', label: 'Live website scraping', block: 'web-fetch', default: true },
              { id: 'ch-data', label: 'Companies House data', block: 'companies-house-lookup', default: true },
              { id: 'crm-cross-ref', label: 'CRM cross-reference', block: 'hubspot-read', default: false }
          ],
          tags: ['batch', 'research', 'prospect'] },

        { id: 'linkedin-company-deep-dive', name: 'Company Deep Dive', icon: '&#127970;', category: 'deal-sourcing',
          impact: 4, complexity: 'Low', status: 'ready', timeSavedMin: 30, estimatedTime: '15-25s',
          description: 'Full company intelligence: employee count, funding, key hires, recent news, competitors.',
          execute: { type: 'ai-query', inputs: [
              { key: 'company', label: 'Company name', type: 'text', required: true },
              { key: 'domain', label: 'Website domain (optional)', type: 'text', placeholder: 'e.g. acme.com' }
          ], buildPayload: function (i) { return { question: 'Provide a comprehensive company deep dive for ' + i.company + (i.domain ? ' (' + i.domain + ')' : '') + '. Include: company overview, founding date, employee count estimate, funding/ownership, key leadership with LinkedIn-style bios, recent news/developments, main competitors, market position, technology stack indicators, and any red/green flags for M&A acquisition.', report: true }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }, { label: '&#128424; Export', handler: 'exportPdf' }] },
          requires: ['groq'],
          blocks: [
              { id: 'ai-analyse', role: 'core' }, { id: 'web-fetch', role: 'enhance' },
              { id: 'companies-house-lookup', role: 'enhance' }, { id: 'dashboard-context', role: 'enhance' },
              { id: 'clipboard-copy', role: 'output' }, { id: 'pdf-export', role: 'output' }
          ],
          features: [
              { id: 'web-scraping', label: 'Live website scraping', block: 'web-fetch', default: true },
              { id: 'ch-data', label: 'Companies House data', block: 'companies-house-lookup', default: true },
              { id: 'crm-cross-ref', label: 'CRM cross-reference', block: 'hubspot-read', default: false }
          ],
          tags: ['company', 'deep-dive', 'intelligence'] },

        { id: 'hubspot-lead-source-audit', name: 'Audit Lead Sources', icon: '&#128294;', category: 'deal-sourcing',
          impact: 4, complexity: 'Medium', status: 'ready', timeSavedMin: 25, estimatedTime: '10-20s',
          description: 'Analyse lead sources by conversion rate with AI recommendations to double down or cut.',
          execute: { type: 'ai-query', inputs: [
              { key: 'period', label: 'Time period', type: 'select', default: '90d', options: [
                  { value: '30d', label: 'Last 30 days' }, { value: '90d', label: 'Last 90 days' },
                  { value: 'ytd', label: 'Year to date' }] }
          ], buildPayload: function (i) { return { question: 'Analyse our lead sources for the ' + i.period + ' period using our CRM data. For each source: count, conversion rate to opportunity, average deal value, and time-to-convert. Recommend which sources to invest more in and which to cut. Use the data available in the dashboard.', report: true }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          requires: ['groq'],
          blocks: [
              { id: 'ai-analyse', role: 'core' }, { id: 'hubspot-read', role: 'enhance' },
              { id: 'dashboard-context', role: 'enhance' }, { id: 'clipboard-copy', role: 'output' }
          ],
          tags: ['audit', 'lead-source', 'analytics'] },

        { id: 'outreach-ab-test-report', name: 'A/B Test Report', icon: '&#129514;', category: 'deal-sourcing',
          impact: 3, complexity: 'Medium', status: 'planned', timeSavedMin: 20, estimatedTime: '10-15s',
          description: 'Compare outreach message variants by reply rate, intent classification, and conversion.',
          execute: { type: 'ai-query', inputs: [
              { key: 'period', label: 'Date range', type: 'select', default: '30d', options: [
                  { value: '7d', label: 'Last 7 days' }, { value: '30d', label: 'Last 30 days' }, { value: '90d', label: 'Last 90 days' }] }
          ], buildPayload: function (i) { return { question: 'Generate an A/B test report for our outreach campaigns over ' + i.period + '. Compare message variants by: reply rate, positive intent rate, meeting booking rate. Recommend the winning copy and suggest improvements.' }; },
            resultType: 'markdown' },
          requires: ['supabase', 'groq'],
          blocks: [
              { id: 'ai-analyse', role: 'core' }, { id: 'data-read', role: 'enhance' },
              { id: 'dashboard-context', role: 'enhance' }
          ],
          tags: ['ab-test', 'outreach', 'analytics'] },

        { id: 'linkedin-profile-enricher', name: 'Enrich Contact', icon: '&#10024;', category: 'deal-sourcing',
          impact: 3, complexity: 'Low', status: 'planned', timeSavedMin: 10, estimatedTime: '5-10s',
          description: 'Enrich a HubSpot contact with LinkedIn data: title, company, headline, location.',
          execute: { type: 'api-call', inputs: [
              { key: 'contact_id', label: 'HubSpot Contact ID', type: 'text', required: true },
              { key: 'linkedin_url', label: 'LinkedIn Profile URL', type: 'text', required: true }
          ], buildPayload: function (i) { return { target: 'linkedin', action: 'enrich', contact_id: i.contact_id, url: i.linkedin_url }; },
            resultType: 'json' },
          requires: ['linkedin', 'hubspot'],
          blocks: [{ id: 'linkedin-profile', role: 'core' }, { id: 'hubspot-write', role: 'core' }],
          tags: ['enrich', 'linkedin', 'hubspot'] }
    ]);
})();
