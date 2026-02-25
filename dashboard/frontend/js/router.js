/* ============================================================
   Router — SPA page navigation, fragment loading, preferences
   ============================================================ */
(function () {
    'use strict';

    var LS_KEY = 'ecomplete_dash_prefs';
    var loaded = {};

    // Page-specific scripts loaded after fragment HTML injection
    var PAGE_SCRIPTS = {
        'monday-pipeline': ['js/monday-pipeline.js'],
        'monday-ic': ['js/monday-ic.js'],
        'ai-roadmap': ['js/ai-roadmap.js'],
        'executive': ['js/pages/render-executive.js'],
        'inbound-queue': ['js/pages/render-inbound.js'],
        'skills': [
            'js/skills/connectors-registry.js',
            'js/skills/blocks-registry.js',
            'js/skills/skills-registry.js',
            'js/skills/skills-deal-sourcing.js',
            'js/skills/skills-nda-legal.js',
            'js/skills/skills-email-comms.js',
            'js/skills/skills-cdd.js',
            'js/skills/skills-pipeline.js',
            'js/skills/skills-ops.js',
            'js/skills/skills-reporting-intel.js',
            'js/skills/skills-engine.js',
            'js/skills/connectors-ui.js',
            'js/skills/skills-expanded.js',
            'js/skills/skills-ui.js'
        ]
    };

    // Page renderers called after scripts load
    var PAGE_RENDERERS = {
        'executive': 'renderExecutive',
        'inbound-queue': 'renderInbound',
        'ma-hub': 'renderMAHub',
        'skills': 'renderSkills'
    };

    // ------------------------------------------------------------------
    // Preferences — localStorage persistence
    // ------------------------------------------------------------------
    window.loadPrefs = function () {
        try { return JSON.parse(localStorage.getItem(LS_KEY) || '{}'); }
        catch (e) { return {}; }
    };

    window.savePrefs = function (updates) {
        try {
            var p = window.loadPrefs();
            for (var k in updates) p[k] = updates[k];
            localStorage.setItem(LS_KEY, JSON.stringify(p));
        } catch (e) { /* empty */ }
    };

    // ------------------------------------------------------------------
    // Fragment loader — lazy-loads page HTML on first visit
    // ------------------------------------------------------------------
    function loadScript(src) {
        return new Promise(function (resolve, reject) {
            var s = document.createElement('script');
            s.src = src;
            s.onload = resolve;
            s.onerror = reject;
            document.body.appendChild(s);
        });
    }

    function loadPage(pageId) {
        if (loaded[pageId]) return Promise.resolve();
        var container = document.getElementById('page-' + pageId);
        if (!container) return Promise.resolve();

        // Show loading skeleton
        container.innerHTML = '<div class="page-loading">'
            + '<div class="skeleton-line" style="width:40%"></div>'
            + '<div class="skeleton-card"></div>'
            + '<div class="skeleton-card"></div>'
            + '</div>';

        return fetch('pages/' + pageId + '.html')
            .then(function (r) {
                if (!r.ok) throw new Error('Failed to load page');
                return r.text();
            })
            .then(function (html) {
                container.innerHTML = html;
                loaded[pageId] = true;
                // Load page-specific scripts sequentially
                var scripts = PAGE_SCRIPTS[pageId];
                if (scripts) {
                    return scripts.reduce(function (chain, src) {
                        return chain.then(function () { return loadScript(src); });
                    }, Promise.resolve());
                }
            })
            .then(function () {
                // Call page renderer if one exists
                var renderer = PAGE_RENDERERS[pageId];
                if (renderer && typeof window[renderer] === 'function') {
                    window[renderer]();
                }
                // Re-apply current filter to populate data on newly loaded page
                if (window.applyFilter && window.currentPeriod) {
                    window.applyFilter(window.currentPeriod);
                }
            })
            .catch(function () {
                container.innerHTML = '<div style="padding:40px;text-align:center;color:#6b7280">'
                    + '<div style="font-size:32px;margin-bottom:8px">&#9888;</div>'
                    + '<div style="font-weight:600;margin-bottom:4px">Failed to load page</div>'
                    + '<button onclick="location.reload()" style="margin-top:12px;padding:8px 16px;'
                    + 'background:var(--accent);color:#fff;border:none;border-radius:8px;cursor:pointer">'
                    + 'Reload</button></div>';
            });
    }

    // ------------------------------------------------------------------
    // SPA page switcher
    // ------------------------------------------------------------------
    window.showPage = function (pageId) {
        // Hide all pages
        document.querySelectorAll('.dash-page').forEach(function (page) {
            page.classList.remove('active');
        });

        // Show target immediately (loading skeleton or cached content)
        var target = document.getElementById('page-' + pageId);
        if (target) target.classList.add('active');

        // Update sidebar active link
        document.querySelectorAll('.sidebar-link').forEach(function (link) {
            link.classList.toggle('active', link.getAttribute('data-page') === pageId);
        });

        // Scroll to top
        var main = document.getElementById('layout-main');
        if (main) main.scrollTop = 0;
        window.scrollTo(0, 0);

        // Load fragment if not cached, then animate cards
        loadPage(pageId).then(function () {
            if (target && window.staggerCards) {
                window.staggerCards(target);
            }
            if (target && window.initCountUps) {
                window.initCountUps(target);
            }
            // Render memory panel + start particles on Anna page
            if (pageId === 'anna') {
                if (window.AIMemory) window.AIMemory.renderMemoryPanel();
                if (window.AIParticles) window.AIParticles.init();
            }
        });

        // Stop particles when leaving Anna page
        if (pageId !== 'anna' && window.AIParticles) window.AIParticles.stop();

        // Hide chat FAB + top bar on Anna page; hide filter bar on non-report pages
        var isAnna = (pageId === 'anna');
        var noFilterPages = ['anna', 'skills', 'ai-roadmap', 'inbound-queue'];
        var fab = document.getElementById('chat-fab');
        var topBar = document.getElementById('top-bar');
        var filterBar = document.getElementById('filter-bar');
        if (fab) fab.style.display = isAnna ? 'none' : '';
        if (topBar) topBar.style.display = isAnna ? 'none' : '';
        if (filterBar) filterBar.style.display = noFilterPages.indexOf(pageId) !== -1 ? 'none' : '';

        // Persist last page
        window.savePrefs({ lastPage: pageId });
    };

    // ------------------------------------------------------------------
    // Event delegation for clickable KPI cards and exec pillars
    // ------------------------------------------------------------------
    document.addEventListener('click', function (e) {
        var card = e.target.closest('[data-nav-page]');
        if (card) window.showPage(card.getAttribute('data-nav-page'));
    });

    // Restore last page on load
    var prefs = window.loadPrefs();
    window.showPage(prefs.lastPage || 'executive');
})();
