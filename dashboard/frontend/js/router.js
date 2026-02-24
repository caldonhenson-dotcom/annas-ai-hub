/* ============================================================
   Router — SPA page navigation, preferences, page init
   ============================================================ */
(function () {
    'use strict';

    // ------------------------------------------------------------------
    // Preferences — localStorage persistence
    // ------------------------------------------------------------------
    var LS_KEY = 'ecomplete_dash_prefs';

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
    // SPA page switcher (#51)
    // ------------------------------------------------------------------
    window.showPage = function (pageId) {
        // Hide all pages
        document.querySelectorAll('.dash-page').forEach(function (page) {
            page.classList.remove('active');
        });
        // Show the target page
        var target = document.getElementById('page-' + pageId);
        if (target) {
            target.classList.add('active');
        }
        // Update sidebar active link
        document.querySelectorAll('.sidebar-link').forEach(function (link) {
            link.classList.toggle('active', link.getAttribute('data-page') === pageId);
        });
        // Scroll to top
        var main = document.getElementById('layout-main');
        if (main) main.scrollTop = 0;
        window.scrollTo(0, 0);
        // Re-trigger entry animations
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
        // Hide chat FAB, freshness bar, and filter bar on Anna page
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

    // Clickable KPI card navigation (#40)
    document.addEventListener('click', function (e) {
        var card = e.target.closest('.stat-card[data-nav-page]');
        if (card) {
            window.showPage(card.getAttribute('data-nav-page'));
        }
    });

    // Exec pillar click-through
    document.querySelectorAll('.exec-pillar[data-nav-page]').forEach(function (p) {
        p.style.cursor = 'pointer';
        p.addEventListener('click', function () {
            window.showPage(p.getAttribute('data-nav-page'));
        });
    });

    // Restore last page on load
    var prefs = window.loadPrefs();
    var startPage = prefs.lastPage || 'executive';
    window.showPage(startPage);
})();
