/* ============================================================
   Skills — NDA & Legal Workflow (8 skills)
   ============================================================ */
(function () {
    'use strict';

    window.SkillsRegistry.registerBatch([
        { id: 'nda-review-inbound', name: 'Review Inbound NDA', icon: '&#128196;', category: 'nda-legal',
          impact: 5, complexity: 'Low', status: 'ready', timeSavedMin: 45, estimatedTime: '15-30s',
          description: 'AI reviews an inbound NDA: flags risky clauses, generates risk assessment (low/medium/high), and recommends actions.',
          execute: { type: 'ai-query', inputs: [
              { key: 'nda_text', label: 'Paste NDA text or key clauses', type: 'textarea', required: true, placeholder: 'Paste the NDA content here...' },
              { key: 'counterparty', label: 'Counterparty name', type: 'text', placeholder: 'e.g. Acme Corp' }
          ], buildPayload: function (i) { return { question: 'You are an experienced M&A legal reviewer. Review this NDA from ' + (i.counterparty || 'the counterparty') + '. Provide:\n1. OVERALL RISK LEVEL (Low/Medium/High)\n2. KEY TERMS SUMMARY (parties, term, governing law, scope)\n3. CLAUSE-BY-CLAUSE ANALYSIS with risk flags for: definition scope, non-compete, non-solicitation, IP assignment, indemnification, survival period, carve-outs, remedies\n4. RED FLAGS (any unusual or one-sided clauses)\n5. RECOMMENDED ACTIONS (accept/negotiate/reject with specific markup suggestions)\n\nNDA Text:\n' + i.nda_text, report: true }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }, { label: '&#128424; Export PDF', handler: 'exportPdf' }] },
          requires: ['groq'],
          blocks: [
              { id: 'ai-analyse', role: 'core' }, { id: 'email-read', role: 'enhance' },
              { id: 'clipboard-copy', role: 'output' }, { id: 'pdf-export', role: 'output' }
          ],
          features: [
              { id: 'email-import', label: 'Import from inbox', block: 'email-read', default: false },
              { id: 'pdf-out', label: 'Export as PDF', block: 'pdf-export', default: true }
          ],
          tags: ['nda', 'review', 'legal', 'risk'] },

        { id: 'nda-send-ecomplete', name: 'Send eComplete NDA', icon: '&#128228;', category: 'nda-legal',
          impact: 4, complexity: 'Medium', status: 'planned', timeSavedMin: 20, estimatedTime: '10-15s',
          description: 'Create and send eComplete\'s mutual NDA via PandaDoc for e-signature, linked to deal.',
          execute: { type: 'api-call', inputs: [
              { key: 'recipient_name', label: 'Recipient name', type: 'text', required: true },
              { key: 'recipient_email', label: 'Recipient email', type: 'text', required: true },
              { key: 'company', label: 'Company name', type: 'text', required: true },
              { key: 'deal_id', label: 'HubSpot Deal ID (optional)', type: 'text' }
          ], buildPayload: function (i) { return { target: 'pandadoc', action: 'send_nda', recipient: i.recipient_name, email: i.recipient_email, company: i.company, deal_id: i.deal_id }; },
            resultType: 'json' },
          requires: ['pandadoc'],
          blocks: [
              { id: 'email-send', role: 'core' }, { id: 'hubspot-read', role: 'enhance' },
              { id: 'notification', role: 'output' }
          ],
          tags: ['nda', 'send', 'pandadoc', 'signature'] },

        { id: 'nda-watch-inbox', name: 'NDA Inbox Watcher', icon: '&#128064;', category: 'nda-legal',
          impact: 5, complexity: 'High', status: 'planned', timeSavedMin: 60, estimatedTime: 'continuous',
          description: 'Monitors inbox for NDA attachments, auto-detects and runs AI review, sends summary alert.',
          execute: { type: 'api-call', inputs: [], buildPayload: function () { return { target: 'gmail', action: 'watch_nda' }; }, resultType: 'json' },
          requires: ['gmail', 'groq'],
          blocks: [
              { id: 'email-read', role: 'core' }, { id: 'ai-analyse', role: 'core' },
              { id: 'notification', role: 'output' }
          ],
          features: [
              { id: 'auto-review', label: 'Auto-review attachments', block: 'ai-analyse', default: true },
              { id: 'alert', label: 'Push notification on detect', block: 'notification', default: true }
          ],
          tags: ['nda', 'inbox', 'watch', 'auto'] },

        { id: 'nda-status-tracker', name: 'NDA Status Dashboard', icon: '&#128203;', category: 'nda-legal',
          impact: 3, complexity: 'Medium', status: 'planned', timeSavedMin: 15, estimatedTime: '5-10s',
          description: 'List all NDAs: sent/viewed/signed/expired, linked to deals, days outstanding.',
          execute: { type: 'api-call', inputs: [
              { key: 'filter', label: 'Filter', type: 'select', default: 'all', options: [
                  { value: 'all', label: 'All NDAs' }, { value: 'pending', label: 'Pending signature' },
                  { value: 'signed', label: 'Signed' }, { value: 'expired', label: 'Expired' }] }
          ], buildPayload: function (i) { return { target: 'pandadoc', action: 'list_ndas', filter: i.filter }; },
            resultType: 'json' },
          requires: ['pandadoc'],
          blocks: [{ id: 'data-read', role: 'core' }, { id: 'dashboard-context', role: 'enhance' }],
          tags: ['nda', 'status', 'tracker'] },

        { id: 'nda-follow-up-chaser', name: 'Chase Unsigned NDAs', icon: '&#9200;', category: 'nda-legal',
          impact: 3, complexity: 'Low', status: 'planned', timeSavedMin: 10, estimatedTime: '5-8s',
          description: 'Send polite reminders to counterparties with unsigned NDAs older than threshold.',
          execute: { type: 'api-call', inputs: [
              { key: 'days', label: 'Days unsigned threshold', type: 'number', default: '5' }
          ], buildPayload: function (i) { return { target: 'pandadoc', action: 'chase_unsigned', days_threshold: parseInt(i.days) || 5 }; },
            resultType: 'json' },
          requires: ['pandadoc', 'gmail'],
          blocks: [{ id: 'data-read', role: 'core' }, { id: 'email-send', role: 'core' }, { id: 'notification', role: 'output' }],
          tags: ['nda', 'chase', 'reminder'] },

        { id: 'nda-redline-compare', name: 'Compare NDA Versions', icon: '&#9878;', category: 'nda-legal',
          impact: 4, complexity: 'Medium', status: 'ready', timeSavedMin: 30, estimatedTime: '15-25s',
          description: 'AI compares two NDA versions: highlights changed, added, and removed clauses with risk delta.',
          execute: { type: 'ai-query', inputs: [
              { key: 'version1', label: 'Original NDA text', type: 'textarea', required: true, placeholder: 'Paste original NDA...' },
              { key: 'version2', label: 'Revised NDA text', type: 'textarea', required: true, placeholder: 'Paste revised NDA...' }
          ], buildPayload: function (i) { return { question: 'Compare these two NDA versions. For each clause that changed:\n1. What was the original text\n2. What is the new text\n3. Is this change favourable, neutral, or unfavourable for us\n4. Risk impact assessment\n\nAlso list any ADDED or REMOVED clauses.\n\nORIGINAL:\n' + i.version1 + '\n\nREVISED:\n' + i.version2, report: true }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }, { label: '&#128424; Export', handler: 'exportPdf' }] },
          requires: ['groq'],
          blocks: [{ id: 'ai-analyse', role: 'core' }, { id: 'clipboard-copy', role: 'output' }, { id: 'pdf-export', role: 'output' }],
          tags: ['nda', 'compare', 'redline', 'legal'] },

        { id: 'nda-clause-extractor', name: 'Extract Key Terms', icon: '&#128270;', category: 'nda-legal',
          impact: 3, complexity: 'Low', status: 'ready', timeSavedMin: 15, estimatedTime: '8-12s',
          description: 'Extract structured key terms from an NDA: parties, term, governing law, IP, non-compete, survival.',
          execute: { type: 'ai-query', inputs: [
              { key: 'nda_text', label: 'NDA text', type: 'textarea', required: true }
          ], buildPayload: function (i) { return { question: 'Extract the following key terms from this NDA in a structured format:\n- Parties (disclosing & receiving)\n- Effective date & term length\n- Governing law & jurisdiction\n- Definition scope (what is confidential)\n- Non-compete clause (yes/no, duration, scope)\n- Non-solicitation clause\n- IP assignment provisions\n- Indemnification terms\n- Survival period\n- Carve-outs/exceptions\n- Remedy provisions\n\nNDA:\n' + i.nda_text }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          requires: ['groq'],
          blocks: [{ id: 'ai-structured', role: 'core' }, { id: 'clipboard-copy', role: 'output' }],
          tags: ['nda', 'extract', 'terms', 'structure'] },

        { id: 'nda-template-customiser', name: 'Customise NDA Template', icon: '&#128295;', category: 'nda-legal',
          impact: 3, complexity: 'Medium', status: 'planned', timeSavedMin: 20, estimatedTime: '10-15s',
          description: 'Generate a customised NDA from eComplete\'s template with specific jurisdiction and clauses.',
          execute: { type: 'ai-query', inputs: [
              { key: 'company', label: 'Counterparty company', type: 'text', required: true },
              { key: 'type', label: 'NDA type', type: 'select', default: 'mutual', options: [
                  { value: 'mutual', label: 'Mutual NDA' }, { value: 'unilateral', label: 'Unilateral (us disclosing)' }] },
              { key: 'jurisdiction', label: 'Jurisdiction', type: 'select', default: 'england', options: [
                  { value: 'england', label: 'England & Wales' }, { value: 'scotland', label: 'Scotland' },
                  { value: 'us_delaware', label: 'Delaware, USA' }] },
              { key: 'special', label: 'Special clauses (optional)', type: 'textarea', placeholder: 'e.g. Extended non-compete, IP carve-out for open source' }
          ], buildPayload: function (i) { return { question: 'Generate a customised ' + i.type + ' NDA between eComplete Ltd and ' + i.company + ', governed by ' + i.jurisdiction + ' law. Include standard M&A confidentiality terms with 2-year term. ' + (i.special ? 'Special requirements: ' + i.special : '') + ' Format as a complete legal document.', report: true }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }, { label: '&#128424; Export', handler: 'exportPdf' }] },
          requires: ['groq'],
          blocks: [{ id: 'ai-draft', role: 'core' }, { id: 'clipboard-copy', role: 'output' }, { id: 'pdf-export', role: 'output' }],
          tags: ['nda', 'template', 'customise', 'generate'] }
    ]);
})();
