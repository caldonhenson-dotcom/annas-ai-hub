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
        'ai-roadmap': ['js/ai-roadmap.js']
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

        // Load fragment if not cached, then animate
        loadPage(pageId).then(function () {
            if (target) {
                target.querySelectorAll('.glass-card, .stat-card').forEach(function (el) {
                    el.style.opacity = '0';
                    el.style.transform = 'translateY(20px)';
                    setTimeout(function () {
                        el.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
                        el.style.opacity = '1';
                        el.style.transform = 'translateY(0)';
                    }, 50);
                });
            }
        });

        // Hide chat FAB, freshness bar, filter bar on Anna page
        var isAnna = (pageId === 'anna');
        var fab = document.getElementById('chat-fab');
        var freshBar = document.getElementById('freshness-bar');
        var filterBar = document.getElementById('filter-bar');
        if (fab) fab.style.display = isAnna ? 'none' : '';
        if (freshBar) freshBar.style.display = isAnna ? 'none' : '';
        if (filterBar) filterBar.style.display = isAnna ? 'none' : '';

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
