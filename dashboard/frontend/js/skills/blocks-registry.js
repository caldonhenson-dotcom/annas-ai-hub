/* ============================================================
   Building Blocks Registry — reusable micro-skills (Layer 2)
   ============================================================ */
(function () {
    'use strict';

    var BLOCKS = [
        { id: 'ai-analyse', name: 'AI Analysis', icon: '&#129302;',
          requires: ['groq', 'claude'], requireMode: 'or',
          desc: 'Send prompt to LLM, get markdown analysis' },

        { id: 'ai-structured', name: 'AI Structured Output', icon: '&#128203;',
          requires: ['groq', 'claude'], requireMode: 'or',
          desc: 'Send prompt to LLM, get JSON output' },

        { id: 'ai-draft', name: 'AI Draft Text', icon: '&#128221;',
          requires: ['groq', 'claude'], requireMode: 'or',
          desc: 'Generate editable draft text' },

        { id: 'hubspot-read', name: 'Read CRM Data', icon: '&#128188;',
          requires: ['hubspot'], requireMode: 'all',
          desc: 'Read contacts, deals, companies from HubSpot' },

        { id: 'hubspot-write', name: 'Write CRM Data', icon: '&#10133;',
          requires: ['hubspot'], requireMode: 'all',
          desc: 'Create or update contacts, deals in HubSpot' },

        { id: 'monday-read', name: 'Read Monday Data', icon: '&#128203;',
          requires: ['monday'], requireMode: 'all',
          desc: 'Query Monday.com boards and items' },

        { id: 'monday-write', name: 'Write Monday Data', icon: '&#128221;',
          requires: ['monday'], requireMode: 'all',
          desc: 'Create or update Monday.com items' },

        { id: 'linkedin-profile', name: 'LinkedIn Profile', icon: '&#128100;',
          requires: ['linkedin'], requireMode: 'all',
          desc: 'Fetch LinkedIn profile data' },

        { id: 'linkedin-message', name: 'LinkedIn Message', icon: '&#128172;',
          requires: ['linkedin'], requireMode: 'all',
          desc: 'Send LinkedIn direct message' },

        { id: 'email-send', name: 'Send Email', icon: '&#9993;',
          requires: ['gmail'], requireMode: 'all',
          desc: 'Send email via Gmail API' },

        { id: 'email-read', name: 'Read Inbox', icon: '&#128229;',
          requires: ['gmail'], requireMode: 'all',
          desc: 'Read and search Gmail inbox' },

        { id: 'web-fetch', name: 'Fetch Web Page', icon: '&#127760;',
          requires: ['web-scraper'], requireMode: 'all',
          desc: 'Scrape and extract data from a URL' },

        { id: 'companies-house-lookup', name: 'Companies House', icon: '&#127970;',
          requires: ['companies-house'], requireMode: 'all',
          desc: 'Look up UK company filings, officers, financials' },

        { id: 'data-store', name: 'Store Data', icon: '&#128451;',
          requires: ['supabase'], requireMode: 'all',
          desc: 'Write data to Supabase' },

        { id: 'data-read', name: 'Read Data', icon: '&#128196;',
          requires: ['supabase'], requireMode: 'all',
          desc: 'Query data from Supabase' },

        { id: 'dashboard-context', name: 'Dashboard Context', icon: '&#128202;',
          requires: ['supabase'], requireMode: 'all',
          desc: 'Fetch current dashboard metrics for AI context' },

        { id: 'pdf-export', name: 'Export PDF', icon: '&#128424;',
          requires: [], requireMode: 'all',
          desc: 'Generate printable PDF from result' },

        { id: 'clipboard-copy', name: 'Copy to Clipboard', icon: '&#128203;',
          requires: [], requireMode: 'all',
          desc: 'Copy result text to clipboard' },

        { id: 'file-upload', name: 'Upload File', icon: '&#128190;',
          requires: ['supabase'], requireMode: 'all',
          desc: 'Upload attachment to Supabase storage' },

        { id: 'notification', name: 'Notification', icon: '&#128276;',
          requires: [], requireMode: 'all',
          desc: 'Show toast notification in dashboard' }
    ];

    var _blocksMap = {};
    BLOCKS.forEach(function (b) { _blocksMap[b.id] = b; });

    function get(id) { return _blocksMap[id] || null; }
    function getAll() { return BLOCKS; }

    function isAvailable(id) {
        var b = _blocksMap[id];
        if (!b) return false;
        if (!b.requires || b.requires.length === 0) return true;
        if (b.requireMode === 'or') {
            return b.requires.some(function (cId) {
                return window.Connectors && window.Connectors.isAvailable(cId);
            });
        }
        return b.requires.every(function (cId) {
            return window.Connectors && window.Connectors.isAvailable(cId);
        });
    }

    function getAvailableFor(skill) {
        if (!skill.blocks) return [];
        return skill.blocks.filter(function (sb) { return isAvailable(sb.id); })
            .map(function (sb) { return sb.id; });
    }

    function getMissing(skill) {
        if (!skill.blocks) return [];
        return skill.blocks.filter(function (sb) { return !isAvailable(sb.id); });
    }

    function getEffectiveStatus(skill) {
        if (!skill.blocks || skill.blocks.length === 0) return skill.status;
        var coreBlocks = skill.blocks.filter(function (b) { return b.role === 'core'; });
        if (coreBlocks.length === 0) return skill.status;
        var allCoreAvailable = coreBlocks.every(function (b) { return isAvailable(b.id); });
        if (!allCoreAvailable) return 'planned';
        var enhanceBlocks = skill.blocks.filter(function (b) { return b.role === 'enhance'; });
        if (enhanceBlocks.length === 0) return 'ready';
        var someEnhanceAvailable = enhanceBlocks.some(function (b) { return isAvailable(b.id); });
        return someEnhanceAvailable ? 'ready' : 'partial';
    }

    window.Blocks = {
        BLOCKS: BLOCKS,
        getAll: getAll,
        get: get,
        isAvailable: isAvailable,
        getAvailableFor: getAvailableFor,
        getMissing: getMissing,
        getEffectiveStatus: getEffectiveStatus
    };
})();
