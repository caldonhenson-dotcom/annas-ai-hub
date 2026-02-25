/* ============================================================
   API Config — Claude key management, token tracking, connection
   ============================================================ */
(function () {
    'use strict';

    var API_KEY_LS = 'ecomplete_claude_key';
    var TOKEN_LS = 'ecomplete_token_usage';
    var PROVIDER_LS = 'ecomplete_ai_provider';

    function getKey() {
        try { return localStorage.getItem(API_KEY_LS) || ''; }
        catch (e) { return ''; }
    }

    function setKey(key) {
        try { localStorage.setItem(API_KEY_LS, key); }
        catch (e) { /* empty */ }
    }

    function getProvider() {
        try { return localStorage.getItem(PROVIDER_LS) || 'groq'; }
        catch (e) { return 'groq'; }
    }

    function setProvider(p) {
        try { localStorage.setItem(PROVIDER_LS, p); }
        catch (e) { /* empty */ }
    }

    // ------------------------------------------------------------------
    // Token tracking — per-session and cumulative
    // ------------------------------------------------------------------
    var sessionTokens = 0;

    function getTokenUsage() {
        try {
            var data = JSON.parse(localStorage.getItem(TOKEN_LS) || '{}');
            return {
                total: data.total || 0,
                today: data.today || 0,
                todayDate: data.todayDate || '',
                cost: data.cost || 0
            };
        } catch (e) {
            return { total: 0, today: 0, todayDate: '', cost: 0 };
        }
    }

    function addTokens(input, output) {
        var tokens = input + output;
        sessionTokens += tokens;
        var usage = getTokenUsage();
        var today = new Date().toISOString().split('T')[0];
        if (usage.todayDate !== today) {
            usage.today = 0;
            usage.todayDate = today;
        }
        usage.total += tokens;
        usage.today += tokens;
        // Claude pricing estimate: ~$3/M input, ~$15/M output (Sonnet)
        usage.cost += (input * 3 + output * 15) / 1000000;
        try { localStorage.setItem(TOKEN_LS, JSON.stringify(usage)); }
        catch (e) { /* empty */ }
        updateTopBarTokens();
    }

    function updateTopBarTokens() {
        var el = document.getElementById('top-bar-token');
        if (!el) return;
        var usage = getTokenUsage();
        var display = sessionTokens > 0 ? fmtTokens(sessionTokens) : fmtTokens(usage.today);
        var label = sessionTokens > 0 ? ' session' : ' today';
        el.innerHTML = '&#9889; ' + display + label;
        el.title = 'Total: ' + fmtTokens(usage.total) + ' | Est. cost: $' + usage.cost.toFixed(4);
    }

    function fmtTokens(n) {
        if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
        if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
        return String(n);
    }

    // ------------------------------------------------------------------
    // Connection status — test API key validity
    // ------------------------------------------------------------------
    function updateConnectionPill(status) {
        var el = document.getElementById('top-bar-status');
        if (!el) return;
        if (status === 'connected') {
            el.innerHTML = '<span class="live-dot"></span> Claude';
            el.style.color = '#16a34a';
        } else if (status === 'groq') {
            el.innerHTML = '<span class="live-dot"></span> Groq';
            el.style.color = '#3CB4AD';
        } else if (status === 'error') {
            el.innerHTML = '&#9888; Key Invalid';
            el.style.color = '#dc2626';
        } else {
            el.innerHTML = '&#9679; No API Key';
            el.style.color = '#6b7280';
        }
    }

    function testConnection() {
        var key = getKey();
        if (!key) {
            updateConnectionPill(getProvider() === 'groq' ? 'groq' : 'none');
            return Promise.resolve(false);
        }
        return fetch('/api/claude-query', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ test: true, apiKey: key })
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.valid) {
                updateConnectionPill('connected');
                setProvider('claude');
                return true;
            }
            updateConnectionPill('error');
            return false;
        })
        .catch(function () {
            // If serverless function not deployed yet, still show key is set
            if (key.startsWith('sk-ant-')) {
                updateConnectionPill('connected');
                setProvider('claude');
                return true;
            }
            updateConnectionPill('error');
            return false;
        });
    }

    // ------------------------------------------------------------------
    // Settings modal
    // ------------------------------------------------------------------
    function openSettings() {
        var overlay = document.getElementById('api-settings-overlay');
        if (overlay) overlay.classList.remove('hidden');
        var input = document.getElementById('api-key-input');
        if (input) {
            var key = getKey();
            input.value = key ? key.substring(0, 12) + '...' : '';
            input.placeholder = key ? 'Key saved (click to change)' : 'sk-ant-api03-...';
        }
        var providerBtns = document.querySelectorAll('.provider-btn');
        var current = getProvider();
        providerBtns.forEach(function (btn) {
            btn.classList.toggle('active', btn.getAttribute('data-provider') === current);
        });
        updateSettingsStatus();
    }

    function closeSettings() {
        var overlay = document.getElementById('api-settings-overlay');
        if (overlay) overlay.classList.add('hidden');
    }

    function saveApiKey() {
        var input = document.getElementById('api-key-input');
        if (!input) return;
        var key = input.value.trim();
        if (!key || key.indexOf('...') !== -1) return; // Don't save masked value
        if (!key.startsWith('sk-ant-')) {
            showSettingsMsg('Key must start with sk-ant-', 'error');
            return;
        }
        setKey(key);
        setProvider('claude');
        input.value = key.substring(0, 12) + '...';
        showSettingsMsg('API key saved. Testing connection...', 'info');
        testConnection().then(function (valid) {
            if (valid) {
                showSettingsMsg('Connected to Claude API', 'success');
            } else {
                showSettingsMsg('Key saved but connection test failed', 'warning');
            }
        });
    }

    function selectProvider(provider) {
        setProvider(provider);
        var providerBtns = document.querySelectorAll('.provider-btn');
        providerBtns.forEach(function (btn) {
            btn.classList.toggle('active', btn.getAttribute('data-provider') === provider);
        });
        if (provider === 'claude' && !getKey()) {
            showSettingsMsg('Enter your Claude API key below', 'info');
        } else if (provider === 'groq') {
            updateConnectionPill('groq');
            showSettingsMsg('Using Groq (free, server-side key)', 'success');
        }
    }

    function removeApiKey() {
        try { localStorage.removeItem(API_KEY_LS); } catch (e) { /* empty */ }
        var input = document.getElementById('api-key-input');
        if (input) input.value = '';
        setProvider('groq');
        updateConnectionPill('groq');
        showSettingsMsg('API key removed. Switched to Groq.', 'info');
        var providerBtns = document.querySelectorAll('.provider-btn');
        providerBtns.forEach(function (btn) {
            btn.classList.toggle('active', btn.getAttribute('data-provider') === 'groq');
        });
    }

    function showSettingsMsg(text, type) {
        var el = document.getElementById('api-settings-msg');
        if (!el) return;
        el.textContent = text;
        el.className = 'api-settings-msg ' + (type || 'info');
        el.style.display = 'block';
    }

    function updateSettingsStatus() {
        var usage = getTokenUsage();
        var el = document.getElementById('api-usage-summary');
        if (!el) return;
        el.innerHTML = '<div>Today: ' + fmtTokens(usage.today) + ' tokens</div>'
            + '<div>All time: ' + fmtTokens(usage.total) + ' tokens</div>'
            + '<div>Est. cost: $' + usage.cost.toFixed(4) + '</div>';
    }

    // ------------------------------------------------------------------
    // API routing helpers — used by chat-widget.js and anna-page.js
    // ------------------------------------------------------------------
    var GROQ_URL = '/api/ai-query';
    var CLAUDE_URL = '/api/claude-query';

    function getApiEndpoint() {
        if (getProvider() === 'claude' && getKey()) return CLAUDE_URL;
        return GROQ_URL;
    }

    function buildPayload(question, hist, opts) {
        var memoryCtx = window.AIMemory ? window.AIMemory.buildMemoryContext() : '';
        var q = memoryCtx ? question + memoryCtx : question;
        var payload = { question: q, history: hist || [] };
        if (opts && opts.report) payload.report = true;
        if (getProvider() === 'claude' && getKey()) payload.apiKey = getKey();
        return payload;
    }

    // ------------------------------------------------------------------
    // Public API
    // ------------------------------------------------------------------
    window.APIConfig = {
        getKey: getKey,
        getProvider: getProvider,
        addTokens: addTokens,
        openSettings: openSettings,
        closeSettings: closeSettings,
        saveApiKey: saveApiKey,
        selectProvider: selectProvider,
        removeApiKey: removeApiKey,
        testConnection: testConnection,
        updateTopBarTokens: updateTopBarTokens
    };
    window.getApiEndpoint = getApiEndpoint;
    window.buildPayload = buildPayload;

    // Init on load
    updateTopBarTokens();
    var provider = getProvider();
    if (provider === 'claude' && getKey()) {
        testConnection();
    } else {
        updateConnectionPill(provider === 'groq' ? 'groq' : 'none');
    }
})();
