/* ============================================================
   AI Memory — context memory, self-learning, dashboard commands
   ============================================================ */
(function () {
    'use strict';

    var MEMORY_KEY = 'ecomplete_ai_memory';
    var STATS_KEY = 'ecomplete_ai_stats';

    // ------------------------------------------------------------------
    // Memory storage — user preferences and learned patterns
    // ------------------------------------------------------------------
    function loadMemory() {
        try { return JSON.parse(localStorage.getItem(MEMORY_KEY) || '{}'); }
        catch (e) { return {}; }
    }

    function saveMemory(mem) {
        try { localStorage.setItem(MEMORY_KEY, JSON.stringify(mem)); }
        catch (e) { /* empty */ }
    }

    function getMemory() {
        var mem = loadMemory();
        return {
            notes: mem.notes || [],
            preferences: mem.preferences || {},
            commonTopics: mem.commonTopics || {}
        };
    }

    function addNote(text) {
        if (!text || !text.trim()) return;
        var mem = loadMemory();
        if (!mem.notes) mem.notes = [];
        if (mem.notes.length >= 20) mem.notes.shift();
        mem.notes.push({ text: text.trim(), added: new Date().toISOString().split('T')[0] });
        saveMemory(mem);
        renderMemoryPanel();
    }

    function removeNote(idx) {
        var mem = loadMemory();
        if (mem.notes && mem.notes[idx] !== undefined) {
            mem.notes.splice(idx, 1);
            saveMemory(mem);
            renderMemoryPanel();
        }
    }

    function setPreference(key, value) {
        var mem = loadMemory();
        if (!mem.preferences) mem.preferences = {};
        mem.preferences[key] = value;
        saveMemory(mem);
    }

    // ------------------------------------------------------------------
    // Conversation stats — track patterns for self-learning
    // ------------------------------------------------------------------
    function loadStats() {
        try { return JSON.parse(localStorage.getItem(STATS_KEY) || '{}'); }
        catch (e) { return {}; }
    }

    function saveStats(stats) {
        try { localStorage.setItem(STATS_KEY, JSON.stringify(stats)); }
        catch (e) { /* empty */ }
    }

    function trackQuestion(text) {
        if (!text) return;
        var stats = loadStats();
        if (!stats.totalQuestions) stats.totalQuestions = 0;
        if (!stats.topics) stats.topics = {};
        if (!stats.recentQuestions) stats.recentQuestions = [];
        stats.totalQuestions++;

        // Track topic frequency
        var topics = extractTopics(text);
        topics.forEach(function (t) {
            stats.topics[t] = (stats.topics[t] || 0) + 1;
        });

        // Keep last 20 questions
        stats.recentQuestions.push({ q: text.substring(0, 80), date: new Date().toISOString().split('T')[0] });
        if (stats.recentQuestions.length > 20) stats.recentQuestions.shift();

        saveStats(stats);
        renderMemoryPanel();
    }

    function extractTopics(text) {
        var topics = [];
        var lower = text.toLowerCase();
        var keywords = {
            pipeline: ['pipeline', 'deal', 'deals', 'stage'],
            leads: ['lead', 'leads', 'mql', 'sql', 'conversion'],
            activity: ['activity', 'activities', 'calls', 'emails', 'meetings'],
            ma: ['m&a', 'acquisition', 'ic ', 'scorecard', 'investment committee'],
            revenue: ['revenue', 'forecast', 'target', 'quota'],
            team: ['rep', 'team', 'performance', 'performer']
        };
        for (var topic in keywords) {
            for (var i = 0; i < keywords[topic].length; i++) {
                if (lower.indexOf(keywords[topic][i]) !== -1) {
                    topics.push(topic);
                    break;
                }
            }
        }
        return topics;
    }

    function getTopTopics(limit) {
        var stats = loadStats();
        if (!stats.topics) return [];
        var entries = Object.entries(stats.topics);
        entries.sort(function (a, b) { return b[1] - a[1]; });
        return entries.slice(0, limit || 5);
    }

    // ------------------------------------------------------------------
    // Build context string for AI prompts
    // ------------------------------------------------------------------
    function buildMemoryContext() {
        var mem = getMemory();
        var stats = loadStats();
        var parts = [];

        if (mem.notes.length > 0) {
            parts.push('User notes:\n' + mem.notes.map(function (n) { return '- ' + n.text; }).join('\n'));
        }

        var prefs = mem.preferences;
        if (prefs && Object.keys(prefs).length > 0) {
            var prefLines = Object.entries(prefs).map(function (e) { return '- ' + e[0] + ': ' + e[1]; });
            parts.push('User preferences:\n' + prefLines.join('\n'));
        }

        var topTopics = getTopTopics(3);
        if (topTopics.length > 0) {
            var topicStr = topTopics.map(function (t) { return t[0] + ' (' + t[1] + 'x)'; }).join(', ');
            parts.push('Most asked topics: ' + topicStr);
        }

        return parts.length > 0 ? '\n\n[User Context]\n' + parts.join('\n') : '';
    }

    // ------------------------------------------------------------------
    // Dashboard commands — parse chat for navigation/action intents
    // ------------------------------------------------------------------
    var DASH_COMMANDS = [
        { patterns: ['show pipeline', 'go to pipeline', 'open pipeline'], action: function () { window.showPage && window.showPage('pipeline'); } },
        { patterns: ['show leads', 'go to leads', 'open leads'], action: function () { window.showPage && window.showPage('leads'); } },
        { patterns: ['show executive', 'go to executive', 'executive summary'], action: function () { window.showPage && window.showPage('executive'); } },
        { patterns: ['show activities', 'go to activities', 'open activities'], action: function () { window.showPage && window.showPage('activities'); } },
        { patterns: ['show insights', 'go to insights', 'open insights'], action: function () { window.showPage && window.showPage('insights'); } },
        { patterns: ['show m&a', 'go to m&a', 'open m&a hub'], action: function () { window.showPage && window.showPage('ma-hub'); } },
        { patterns: ['show targets', 'go to targets', 'open targets'], action: function () { window.showPage && window.showPage('targets'); } },
        { patterns: ['show roadmap', 'ai roadmap', 'open roadmap'], action: function () { window.showPage && window.showPage('ai-roadmap'); } },
        { patterns: ['show inbound', 'open inbound', 'inbound queue'], action: function () { window.showPage && window.showPage('inbound-queue'); } },
        { patterns: ['show outreach', 'open outreach', 'outreach engine'], action: function () { window.showPage && window.showPage('outreach'); } },
        { patterns: ['dark mode', 'switch to dark', 'enable dark'], action: function () { if (document.documentElement.getAttribute('data-theme') !== 'dark') window.toggleTheme && window.toggleTheme(); } },
        { patterns: ['light mode', 'switch to light', 'enable light'], action: function () { if (document.documentElement.getAttribute('data-theme') === 'dark') window.toggleTheme && window.toggleTheme(); } },
        { patterns: ['open settings', 'api settings', 'change provider'], action: function () { window.APIConfig && window.APIConfig.openSettings(); } }
    ];

    function checkDashboardCommand(text) {
        if (!text) return null;
        var lower = text.toLowerCase().trim();
        for (var i = 0; i < DASH_COMMANDS.length; i++) {
            var cmd = DASH_COMMANDS[i];
            for (var j = 0; j < cmd.patterns.length; j++) {
                if (lower.indexOf(cmd.patterns[j]) !== -1) {
                    return cmd;
                }
            }
        }
        return null;
    }

    // ------------------------------------------------------------------
    // Memory panel UI (rendered into anna sidebar)
    // ------------------------------------------------------------------
    function renderMemoryPanel() {
        var container = document.getElementById('anna-memory-panel');
        if (!container) return;
        var mem = getMemory();
        var stats = loadStats();
        var html = '';

        // Notes section
        html += '<div class="anna-sidebar-label">&#129504; Memory Notes</div>';
        if (mem.notes.length === 0) {
            html += '<div class="anna-memory-empty">No notes yet. Add context for better responses.</div>';
        } else {
            mem.notes.forEach(function (note, idx) {
                html += '<div class="anna-memory-item">'
                    + '<span class="anna-memory-text">' + escHtml(note.text) + '</span>'
                    + '<button class="anna-memory-delete" onclick="window.AIMemory.removeNote(' + idx + ')" title="Remove">&#10005;</button>'
                    + '</div>';
            });
        }
        html += '<div class="anna-memory-add">'
            + '<input class="anna-memory-input" id="anna-memory-input" type="text" placeholder="Add a note..." '
            + 'onkeydown="if(event.key===\'Enter\'){window.AIMemory.addNote(this.value);this.value=\'\';}" />'
            + '</div>';

        // Learning insights
        var topTopics = getTopTopics(4);
        if (topTopics.length > 0 || (stats.totalQuestions && stats.totalQuestions > 0)) {
            html += '<div class="anna-sidebar-divider"></div>';
            html += '<div class="anna-sidebar-label">&#127891; Learned Patterns</div>';
            if (stats.totalQuestions) {
                html += '<div class="anna-memory-stat">' + stats.totalQuestions + ' questions asked</div>';
            }
            topTopics.forEach(function (t) {
                var pct = Math.min(100, Math.round((t[1] / (stats.totalQuestions || 1)) * 100));
                html += '<div class="anna-memory-topic">'
                    + '<span class="anna-memory-topic-name">' + t[0] + '</span>'
                    + '<div class="anna-memory-topic-bar"><div style="width:' + pct + '%"></div></div>'
                    + '<span class="anna-memory-topic-count">' + t[1] + '</span>'
                    + '</div>';
            });
        }

        container.innerHTML = html;
    }

    // ------------------------------------------------------------------
    // Public API
    // ------------------------------------------------------------------
    window.AIMemory = {
        addNote: addNote,
        removeNote: removeNote,
        setPreference: setPreference,
        getMemory: getMemory,
        trackQuestion: trackQuestion,
        buildMemoryContext: buildMemoryContext,
        checkDashboardCommand: checkDashboardCommand,
        renderMemoryPanel: renderMemoryPanel
    };
})();
