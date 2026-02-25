/* ============================================================
   Connectors Registry — authenticated API connections (Layer 1)
   ============================================================ */
(function () {
    'use strict';

    var _status = {};
    var _listeners = [];

    var CONNECTORS = [
        { id: 'groq', name: 'Groq AI', icon: '&#129302;', color: '#f97316',
          authType: 'env-key', capabilities: ['ai-analyse', 'ai-structured', 'ai-draft'],
          healthCheck: function () {
              return fetch(window.getApiEndpoint ? window.getApiEndpoint() : '/api/ai-query', {
                  method: 'POST', headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ question: 'ping', test: true })
              }).then(function (r) { return r.ok; }).catch(function () { return false; });
          }
        },
        { id: 'claude', name: 'Claude AI', icon: '&#129302;', color: '#6366f1',
          authType: 'client-key', capabilities: ['ai-analyse', 'ai-structured', 'ai-draft'],
          healthCheck: function () {
              var k = window.APIConfig && window.APIConfig.getKey();
              if (!k) return Promise.resolve(false);
              return fetch('/api/claude-query', {
                  method: 'POST', headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ test: true, apiKey: k })
              }).then(function (r) { return r.ok; }).catch(function () { return false; });
          }
        },
        { id: 'hubspot', name: 'HubSpot CRM', icon: '&#128188;', color: '#ff7a59',
          authType: 'env-key', capabilities: ['hubspot-read', 'hubspot-write'],
          healthCheck: function () { return _serverHealth('hubspot'); }
        },
        { id: 'monday', name: 'Monday.com', icon: '&#128203;', color: '#6161ff',
          authType: 'env-key', capabilities: ['monday-read', 'monday-write'],
          healthCheck: function () { return _serverHealth('monday'); }
        },
        { id: 'linkedin', name: 'LinkedIn', icon: '&#128100;', color: '#0a66c2',
          authType: 'session', capabilities: ['linkedin-profile', 'linkedin-message'],
          healthCheck: function () {
              return fetch('/api/linkedin-session').then(function (r) {
                  return r.ok ? r.json() : { authenticated: false };
              }).then(function (d) { return !!d.authenticated; }).catch(function () { return false; });
          }
        },
        { id: 'supabase', name: 'Supabase', icon: '&#128451;', color: '#3ecf8e',
          authType: 'env-key', capabilities: ['data-store', 'data-read', 'dashboard-context', 'file-upload'],
          healthCheck: function () { return _serverHealth('supabase'); }
        },
        { id: 'gmail', name: 'Gmail', icon: '&#9993;', color: '#ea4335',
          authType: 'oauth', capabilities: ['email-send', 'email-read'],
          authUrl: '/api/gmail-auth',
          healthCheck: function () {
              return fetch('/api/gmail-auth?action=status').then(function (r) {
                  return r.ok ? r.json() : { connected: false };
              }).then(function (d) { return !!d.connected; }).catch(function () { return false; });
          }
        },
        { id: 'companies-house', name: 'Companies House', icon: '&#127970;', color: '#00703c',
          authType: 'public', capabilities: ['companies-house-lookup'],
          healthCheck: function () { return _serverHealth('companies-house'); }
        },
        { id: 'web-scraper', name: 'Web Scraper', icon: '&#127760;', color: '#64748b',
          authType: 'env-key', capabilities: ['web-fetch'],
          healthCheck: function () { return _serverHealth('web-scraper'); }
        }
    ];

    // Server-side batch health check helper
    function _serverHealth(connectorId) {
        if (_serverHealthCache && _serverHealthCache[connectorId] !== undefined) {
            return Promise.resolve(_serverHealthCache[connectorId]);
        }
        return Promise.resolve(false);
    }

    var _serverHealthCache = null;

    function _fetchServerHealth() {
        return fetch('/api/connector-health').then(function (r) {
            return r.ok ? r.json() : {};
        }).then(function (data) {
            _serverHealthCache = data;
            return data;
        }).catch(function () { _serverHealthCache = {}; return {}; });
    }

    function _notify() {
        var snapshot = {};
        CONNECTORS.forEach(function (c) { snapshot[c.id] = _status[c.id] || 'not-configured'; });
        _listeners.forEach(function (fn) { try { fn(snapshot); } catch (e) { /* empty */ } });
    }

    function checkHealth(id) {
        var c = get(id);
        if (!c) return Promise.resolve(false);
        _status[id] = 'checking';
        _notify();
        return c.healthCheck().then(function (ok) {
            _status[id] = ok ? 'connected' : 'disconnected';
            _notify();
            return ok;
        }).catch(function () {
            _status[id] = 'disconnected';
            _notify();
            return false;
        });
    }

    function checkAll() {
        return _fetchServerHealth().then(function () {
            return Promise.all(CONNECTORS.map(function (c) { return checkHealth(c.id); }));
        });
    }

    function get(id) {
        return CONNECTORS.find(function (c) { return c.id === id; }) || null;
    }

    function getStatus(id) { return _status[id] || 'not-configured'; }
    function isAvailable(id) { return _status[id] === 'connected'; }

    function getByCapability(cap) {
        return CONNECTORS.filter(function (c) {
            return c.capabilities.indexOf(cap) !== -1 && isAvailable(c.id);
        });
    }

    window.Connectors = {
        CONNECTORS: CONNECTORS,
        getAll: function () { return CONNECTORS; },
        get: get,
        getStatus: getStatus,
        checkHealth: checkHealth,
        checkAll: checkAll,
        isAvailable: isAvailable,
        getByCapability: getByCapability,
        onStatusChange: function (fn) { _listeners.push(fn); }
    };
})();
