/* ============================================================
   Skills — Email & Communication (13 skills)
   ============================================================ */
(function () {
    'use strict';

    window.SkillsRegistry.registerBatch([
        { id: 'email-ai-responder', name: 'AI Email Responder', icon: '&#129302;', category: 'email-comms',
          impact: 5, complexity: 'Low', status: 'ready', timeSavedMin: 30, estimatedTime: '10-20s',
          description: 'AI drafts a contextual reply to a complex email, matching tone and referencing deal context.',
          execute: { type: 'ai-query', inputs: [
              { key: 'email', label: 'Paste the email to reply to', type: 'textarea', required: true },
              { key: 'tone', label: 'Tone', type: 'select', default: 'professional', options: [
                  { value: 'professional', label: 'Professional' }, { value: 'friendly', label: 'Friendly' },
                  { value: 'formal', label: 'Formal' }, { value: 'brief', label: 'Brief & Direct' }] },
              { key: 'context', label: 'Additional context (optional)', type: 'textarea', placeholder: 'e.g. We are in NDA stage, they want to discuss valuation' }
          ], buildPayload: function (i) { return { question: 'Draft a ' + i.tone + ' email reply to this message. ' + (i.context ? 'Context: ' + i.context + '. ' : '') + 'I am Anna, MD at eComplete, an M&A advisory firm. Keep it concise, actionable, and professional.\n\nEmail to reply to:\n' + i.email }; },
            resultType: 'draft', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          requires: ['groq'],
          blocks: [
              { id: 'ai-draft', role: 'core' }, { id: 'email-read', role: 'enhance' },
              { id: 'email-send', role: 'enhance' }, { id: 'clipboard-copy', role: 'output' }
          ],
          features: [
              { id: 'auto-send', label: 'Send after approval', block: 'email-send', default: false },
              { id: 'deal-context', label: 'Inject deal context', block: 'dashboard-context', default: true }
          ],
          tags: ['email', 'reply', 'ai', 'draft'] },

        { id: 'email-schedule-meeting', name: 'Schedule Meeting', icon: '&#128197;', category: 'email-comms',
          impact: 3, complexity: 'Low', status: 'ready', timeSavedMin: 10, estimatedTime: '8-12s',
          description: 'Draft a meeting scheduling email with availability and booking link.',
          execute: { type: 'ai-query', inputs: [
              { key: 'recipient', label: 'Recipient name', type: 'text', required: true },
              { key: 'meeting_type', label: 'Meeting type', type: 'select', default: 'intro', options: [
                  { value: 'intro', label: 'Introduction call' }, { value: 'follow_up', label: 'Follow-up' },
                  { value: 'london', label: 'London meeting' }, { value: 'deal_review', label: 'Deal review' }] },
              { key: 'notes', label: 'Additional notes', type: 'textarea', placeholder: 'e.g. Prefer mornings, need 30 mins' }
          ], buildPayload: function (i) { return { question: 'Draft a meeting scheduling email to ' + i.recipient + ' for a ' + i.meeting_type + ' meeting. I am Anna, MD at eComplete. Include a professional greeting, purpose of meeting, suggest 2-3 time slots this week/next week, and close with contact details. ' + (i.notes || '') }; },
            resultType: 'draft', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          requires: ['groq'],
          blocks: [{ id: 'ai-draft', role: 'core' }, { id: 'dashboard-context', role: 'enhance' }, { id: 'clipboard-copy', role: 'output' }],
          tags: ['meeting', 'schedule', 'email', 'calendar'] },

        { id: 'email-send-info-pack', name: 'Send Info Pack', icon: '&#128230;', category: 'email-comms',
          impact: 3, complexity: 'Low', status: 'ready', timeSavedMin: 15, estimatedTime: '10-15s',
          description: 'Draft an information pack email with deal highlights for a prospect or advisor.',
          execute: { type: 'ai-query', inputs: [
              { key: 'recipient', label: 'Recipient name & company', type: 'text', required: true },
              { key: 'deal_name', label: 'Deal/project name', type: 'text', required: true },
              { key: 'highlights', label: 'Key highlights to include', type: 'textarea', placeholder: 'e.g. Revenue: £5M, 30% YoY growth, SaaS model, 200+ enterprise clients' }
          ], buildPayload: function (i) { return { question: 'Draft a professional info pack cover email from Anna (MD, eComplete) to ' + i.recipient + ' about ' + i.deal_name + '. Include: brief intro to eComplete, deal highlights (' + i.highlights + '), why this is a compelling opportunity, and next steps. Professional but not overly formal.' }; },
            resultType: 'draft', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          requires: ['groq'],
          blocks: [
              { id: 'ai-draft', role: 'core' }, { id: 'hubspot-read', role: 'enhance' },
              { id: 'file-upload', role: 'enhance' }, { id: 'clipboard-copy', role: 'output' }
          ],
          tags: ['info-pack', 'email', 'deal'] },

        { id: 'email-follow-up-post-meeting', name: 'Post-Meeting Follow-Up', icon: '&#9998;', category: 'email-comms',
          impact: 3, complexity: 'Low', status: 'ready', timeSavedMin: 15, estimatedTime: '10-15s',
          description: 'AI structures a post-meeting follow-up email with summary and next steps.',
          execute: { type: 'ai-query', inputs: [
              { key: 'attendees', label: 'Attendees', type: 'text', required: true, placeholder: 'e.g. John Smith (Acme), Sarah Jones (eComplete)' },
              { key: 'notes', label: 'Meeting notes (rough)', type: 'textarea', required: true, placeholder: 'Key discussion points, decisions, action items...' }
          ], buildPayload: function (i) { return { question: 'Draft a post-meeting follow-up email from Anna (MD, eComplete) to the attendees: ' + i.attendees + '. Structure it as: 1) Thank you for the meeting, 2) Key discussion points summary, 3) Decisions made, 4) Action items with owners, 5) Next steps and timeline. Meeting notes:\n' + i.notes }; },
            resultType: 'draft', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          requires: ['groq'],
          blocks: [{ id: 'ai-draft', role: 'core' }, { id: 'dashboard-context', role: 'enhance' }, { id: 'clipboard-copy', role: 'output' }],
          tags: ['follow-up', 'meeting', 'email', 'summary'] },

        { id: 'email-polite-decline', name: 'Send Polite Decline', icon: '&#128075;', category: 'email-comms',
          impact: 2, complexity: 'Low', status: 'ready', timeSavedMin: 5, estimatedTime: '5-8s',
          description: 'Draft a professional but warm decline email for opportunities that are not a fit.',
          execute: { type: 'ai-query', inputs: [
              { key: 'recipient', label: 'Recipient', type: 'text', required: true },
              { key: 'reason', label: 'Reason (optional)', type: 'select', default: 'not_fit', options: [
                  { value: 'not_fit', label: 'Not a strategic fit' }, { value: 'too_small', label: 'Below size threshold' },
                  { value: 'sector', label: 'Outside sector focus' }, { value: 'timing', label: 'Bad timing' }] }
          ], buildPayload: function (i) { return { question: 'Draft a polite, warm decline email from Anna (MD, eComplete) to ' + i.recipient + '. Reason: ' + i.reason + '. Be gracious, leave the door open for future opportunities, wish them well. Keep it short (5-6 sentences).' }; },
            resultType: 'draft', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          requires: ['groq'],
          blocks: [{ id: 'ai-draft', role: 'core' }, { id: 'clipboard-copy', role: 'output' }],
          tags: ['decline', 'email', 'polite'] },

        { id: 'email-request-more-info', name: 'Request More Info', icon: '&#10067;', category: 'email-comms',
          impact: 2, complexity: 'Low', status: 'ready', timeSavedMin: 5, estimatedTime: '5-8s',
          description: 'Draft a request for additional information email (revenue, EBITDA, overview docs).',
          execute: { type: 'ai-query', inputs: [
              { key: 'recipient', label: 'Recipient', type: 'text', required: true },
              { key: 'deal', label: 'Deal/company name', type: 'text', required: true },
              { key: 'info_needed', label: 'Information needed', type: 'textarea', placeholder: 'e.g. Last 3 years revenue, EBITDA, customer concentration, team structure' }
          ], buildPayload: function (i) { return { question: 'Draft a professional email from Anna (MD, eComplete) to ' + i.recipient + ' requesting additional information about ' + i.deal + '. We need: ' + (i.info_needed || 'revenue (last 3 years), EBITDA, customer concentration, team structure, and any overview deck') + '. Be respectful of their time, explain why we need it (standard due diligence process).' }; },
            resultType: 'draft', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          requires: ['groq'],
          blocks: [{ id: 'ai-draft', role: 'core' }, { id: 'hubspot-read', role: 'enhance' }, { id: 'clipboard-copy', role: 'output' }],
          tags: ['request', 'info', 'email', 'due-diligence'] },

        { id: 'email-inbox-triage', name: 'AI Inbox Triage', icon: '&#128229;', category: 'email-comms',
          impact: 5, complexity: 'High', status: 'ready', timeSavedMin: 45, estimatedTime: '15-30s',
          description: 'AI scans inbox descriptions, classifies priority, matches to contacts, generates action list.',
          execute: { type: 'ai-query', inputs: [
              { key: 'emails', label: 'Paste email subjects and senders (one per line)', type: 'textarea', required: true, placeholder: 'From: John Smith (Acme) - Re: NDA Review\nFrom: Sarah (Legal) - Urgent: Contract amendment\nFrom: Newsletter - Weekly M&A roundup' }
          ], buildPayload: function (i) { return { question: 'Triage these inbox items for an M&A advisory MD. For each email, classify:\n- PRIORITY: Urgent / Needs Reply / FYI / Low Priority / Spam\n- ACTION: Reply needed / Schedule meeting / Forward to team / File / Delete\n- DEAL LINK: If related to a deal, note which one\n\nThen provide a prioritised ACTION LIST (top 5 most important things to do first).\n\nEmails:\n' + i.emails, report: true }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          requires: ['groq'],
          blocks: [
              { id: 'ai-analyse', role: 'core' }, { id: 'email-read', role: 'enhance' },
              { id: 'dashboard-context', role: 'enhance' }
          ],
          features: [
              { id: 'live-inbox', label: 'Scan live inbox', block: 'email-read', default: false },
              { id: 'deal-match', label: 'Match to CRM deals', block: 'dashboard-context', default: true }
          ],
          tags: ['inbox', 'triage', 'priority', 'email'] },

        { id: 'team-chaser-overdue', name: 'Chase Overdue Tasks', icon: '&#128227;', category: 'email-comms',
          impact: 4, complexity: 'Low', status: 'ready', timeSavedMin: 20, estimatedTime: '10-15s',
          description: 'AI drafts personalised chase emails for team members with overdue Monday.com items.',
          execute: { type: 'ai-query', inputs: [
              { key: 'team_member', label: 'Team member name', type: 'text', required: true },
              { key: 'overdue_items', label: 'Overdue items (paste from Monday)', type: 'textarea', required: true, placeholder: 'Item 1: CDD Report for Acme - due 3 days ago\nItem 2: NDA follow-up - due 5 days ago' },
              { key: 'tone', label: 'Tone', type: 'select', default: 'firm-but-friendly', options: [
                  { value: 'gentle', label: 'Gentle reminder' }, { value: 'firm-but-friendly', label: 'Firm but friendly' },
                  { value: 'urgent', label: 'Urgent' }] }
          ], buildPayload: function (i) { return { question: 'Draft a ' + i.tone + ' chase email from Anna (MD) to ' + i.team_member + ' about these overdue items:\n' + i.overdue_items + '\n\nBe specific about each item, ask for an update and revised completion date. If urgent tone, emphasise impact on deal timelines.' }; },
            resultType: 'draft', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          requires: ['groq'],
          blocks: [
              { id: 'ai-draft', role: 'core' }, { id: 'monday-read', role: 'enhance' },
              { id: 'email-send', role: 'enhance' }, { id: 'clipboard-copy', role: 'output' }
          ],
          tags: ['chase', 'overdue', 'team', 'monday'] },

        { id: 'team-chaser-deal-update', name: 'Chase Deal Updates', icon: '&#128276;', category: 'email-comms',
          impact: 3, complexity: 'Low', status: 'ready', timeSavedMin: 15, estimatedTime: '10-15s',
          description: 'Draft chase emails to deal owners for deals with no updates in X days.',
          execute: { type: 'ai-query', inputs: [
              { key: 'deal_owner', label: 'Deal owner name', type: 'text', required: true },
              { key: 'deals', label: 'Stale deals (name + days since update)', type: 'textarea', required: true, placeholder: 'Acme Ltd - 18 days since last update\nGlobex Corp - 12 days' }
          ], buildPayload: function (i) { return { question: 'Draft a professional chase email from Anna (MD) to ' + i.deal_owner + ' about these stale deals:\n' + i.deals + '\nAsk for: current status, any blockers, next steps planned, and whether the deal is still active. Be constructive, not punitive.' }; },
            resultType: 'draft', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          requires: ['groq'],
          blocks: [
              { id: 'ai-draft', role: 'core' }, { id: 'hubspot-read', role: 'enhance' },
              { id: 'email-send', role: 'enhance' }, { id: 'clipboard-copy', role: 'output' }
          ],
          tags: ['chase', 'deal', 'update', 'stale'] },

        { id: 'team-chaser-ic-prep', name: 'Chase IC Preparation', icon: '&#128203;', category: 'email-comms',
          impact: 3, complexity: 'Low', status: 'ready', timeSavedMin: 15, estimatedTime: '8-12s',
          description: 'Draft chase emails to team members responsible for IC paper preparation.',
          execute: { type: 'ai-query', inputs: [
              { key: 'ic_date', label: 'IC meeting date', type: 'text', required: true, placeholder: 'e.g. Friday 28th Feb' },
              { key: 'papers_needed', label: 'Papers/items needed', type: 'textarea', required: true, placeholder: 'Deal summary for Acme (John)\nFinancial model update (Sarah)\nCDD status report (Mike)' }
          ], buildPayload: function (i) { return { question: 'Draft an IC preparation chase email from Anna (MD) to the team. IC meeting is on ' + i.ic_date + '. The following papers/items are needed:\n' + i.papers_needed + '\nRemind them of the deadline (24h before IC), ask them to confirm completion status, and emphasise the importance of being well-prepared.' }; },
            resultType: 'draft', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          requires: ['groq'],
          blocks: [
              { id: 'ai-draft', role: 'core' }, { id: 'monday-read', role: 'enhance' },
              { id: 'email-send', role: 'enhance' }, { id: 'clipboard-copy', role: 'output' }
          ],
          tags: ['ic', 'preparation', 'chase', 'meeting'] },

        { id: 'email-bulk-personalised', name: 'Bulk Personalised Email', icon: '&#128231;', category: 'email-comms',
          impact: 5, complexity: 'High', status: 'ready', timeSavedMin: 60, estimatedTime: '30-60s',
          description: 'AI generates unique personalised emails for a list of contacts with shared purpose.',
          execute: { type: 'ai-query', inputs: [
              { key: 'contacts', label: 'Contact list (name, company - one per line)', type: 'textarea', required: true, placeholder: 'John Smith, Acme Ltd\nSarah Jones, Globex Corp\nMike Chen, Initech' },
              { key: 'purpose', label: 'Email purpose', type: 'text', required: true, placeholder: 'e.g. Invite to eComplete networking event' },
              { key: 'template', label: 'Key message points', type: 'textarea', placeholder: 'e.g. Event on March 15th, networking + keynote, RSVP by March 1st' }
          ], buildPayload: function (i) { return { question: 'Generate personalised emails from Anna (MD, eComplete) to each of these contacts. Purpose: ' + i.purpose + '. Key message: ' + (i.template || '') + '. Make each email unique with personalised opening line referencing their company/role. Keep each under 150 words.\n\nContacts:\n' + i.contacts, report: true }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy All', handler: 'copyResult' }] },
          requires: ['groq'],
          blocks: [
              { id: 'ai-draft', role: 'core' }, { id: 'hubspot-read', role: 'enhance' },
              { id: 'email-send', role: 'enhance' }, { id: 'data-store', role: 'enhance' }
          ],
          features: [
              { id: 'crm-enrich', label: 'Enrich from CRM data', block: 'hubspot-read', default: true },
              { id: 'batch-send', label: 'Batch send via Gmail', block: 'email-send', default: false }
          ],
          tags: ['bulk', 'personalised', 'email', 'outreach'] },

        { id: 'email-thread-summariser', name: 'Summarise Email Thread', icon: '&#128220;', category: 'email-comms',
          impact: 3, complexity: 'Low', status: 'ready', timeSavedMin: 10, estimatedTime: '8-12s',
          description: 'AI summarises a long email thread: key points, decisions, action items, next steps.',
          execute: { type: 'ai-query', inputs: [
              { key: 'thread', label: 'Paste the email thread', type: 'textarea', required: true }
          ], buildPayload: function (i) { return { question: 'Summarise this email thread for an M&A advisory MD. Provide:\n1. PARTICIPANTS (who was involved)\n2. KEY POINTS (main discussion topics)\n3. DECISIONS MADE\n4. ACTION ITEMS (with owners if identifiable)\n5. NEXT STEPS\n6. OPEN QUESTIONS\n\nEmail thread:\n' + i.thread, report: true }; },
            resultType: 'markdown', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          requires: ['groq'],
          blocks: [{ id: 'ai-analyse', role: 'core' }, { id: 'clipboard-copy', role: 'output' }],
          tags: ['email', 'summary', 'thread'] },

        { id: 'email-auto-acknowledge', name: 'Auto-Acknowledge Inbound', icon: '&#9989;', category: 'email-comms',
          impact: 2, complexity: 'Low', status: 'ready', timeSavedMin: 5, estimatedTime: '5-8s',
          description: 'Draft a quick acknowledgement email with booking link to buy time for proper review.',
          execute: { type: 'ai-query', inputs: [
              { key: 'sender', label: 'Sender name', type: 'text', required: true },
              { key: 'subject', label: 'Email subject', type: 'text', required: true }
          ], buildPayload: function (i) { return { question: 'Draft a brief (3-4 sentence) acknowledgement email from Anna (MD, eComplete) to ' + i.sender + ' regarding "' + i.subject + '". Confirm receipt, mention will review and respond properly within 24-48 hours, offer to schedule a call if urgent (include a generic booking link placeholder). Warm and professional.' }; },
            resultType: 'draft', actions: [{ label: '&#128203; Copy', handler: 'copyResult' }] },
          requires: ['groq'],
          blocks: [{ id: 'ai-draft', role: 'core' }, { id: 'email-send', role: 'enhance' }, { id: 'clipboard-copy', role: 'output' }],
          tags: ['acknowledge', 'auto', 'reply', 'email'] }
    ]);
})();
