/* ============================================================
   Skills Registry — definition storage, search, categories
   ============================================================ */
(function () {
    'use strict';

    var _skills = {};

    var CATEGORIES = {
        'deal-sourcing':   { id: 'deal-sourcing',   name: 'Deal Sourcing & Outreach',   icon: '&#128640;', color: '#8b5cf6' },
        'nda-legal':       { id: 'nda-legal',       name: 'NDA & Legal',                icon: '&#128220;', color: '#ef4444' },
        'email-comms':     { id: 'email-comms',     name: 'Email & Communication',      icon: '&#9993;',   color: '#3b82f6' },
        'cdd':             { id: 'cdd',             name: 'Commercial Due Diligence',   icon: '&#128269;', color: '#f59e0b' },
        'pipeline':        { id: 'pipeline',        name: 'Deal Pipeline',              icon: '&#128188;', color: '#10b981' },
        'ops':             { id: 'ops',             name: 'Operations',                 icon: '&#9881;',   color: '#6366f1' },
        'board-reporting': { id: 'board-reporting', name: 'Board & Investor Reporting', icon: '&#128202;', color: '#ec4899' },
        'intel':           { id: 'intel',           name: 'Market Intelligence',        icon: '&#127758;', color: '#14b8a6' },
        'data':            { id: 'data',            name: 'Data & Systems',             icon: '&#128451;', color: '#64748b' },
        'portfolio':       { id: 'portfolio',       name: 'Portfolio & E-Commerce',     icon: '&#128722;', color: '#f97316' }
    };

    function register(skill) {
        if (!skill || !skill.id) return;
        _skills[skill.id] = skill;
    }

    function registerBatch(skills) {
        if (!Array.isArray(skills)) return;
        skills.forEach(register);
    }

    function get(id) {
        return _skills[id] || null;
    }

    function getAll() {
        return Object.values(_skills);
    }

    function getByCategory(catId) {
        return Object.values(_skills).filter(function (s) {
            return s.category === catId;
        });
    }

    function search(query) {
        if (!query) return getAll();
        var lower = query.toLowerCase();
        return Object.values(_skills).filter(function (s) {
            return s.name.toLowerCase().indexOf(lower) !== -1
                || s.description.toLowerCase().indexOf(lower) !== -1
                || (s.tags && s.tags.some(function (t) {
                    return t.toLowerCase().indexOf(lower) !== -1;
                }));
        });
    }

    function getStats() {
        var all = Object.values(_skills);
        return {
            total: all.length,
            ready: all.filter(function (s) { return s.status === 'ready'; }).length,
            partial: all.filter(function (s) { return s.status === 'partial'; }).length,
            planned: all.filter(function (s) { return s.status === 'planned'; }).length
        };
    }

    function getTotalTimeSaved() {
        var hist = [];
        try { hist = JSON.parse(localStorage.getItem('ecomplete_skill_history') || '[]'); }
        catch (e) { /* empty */ }
        var today = new Date().toISOString().substring(0, 10);
        var todayRuns = hist.filter(function (h) {
            return h.success && h.timestamp && new Date(h.timestamp).toISOString().substring(0, 10) === today;
        });
        var total = 0;
        todayRuns.forEach(function (h) {
            var skill = _skills[h.skillId];
            if (skill && skill.timeSavedMin) total += skill.timeSavedMin;
        });
        return total;
    }

    window.SkillsRegistry = {
        register: register,
        registerBatch: registerBatch,
        get: get,
        getAll: getAll,
        getByCategory: getByCategory,
        search: search,
        getCategories: function () { return CATEGORIES; },
        getStats: getStats,
        getTotalTimeSaved: getTotalTimeSaved,
        CATEGORIES: CATEGORIES
    };
})();
