/* ============================================================
   App Init — login gate, sidebar toggle, bootstrap
   ============================================================ */
(function () {
    'use strict';

    // ------------------------------------------------------------------
    // Login gate — localStorage name persistence
    // ------------------------------------------------------------------
    var LOGIN_KEY = 'ecomplete_user';
    var loginOverlay = document.getElementById('login-overlay');
    var loginInput = document.getElementById('login-name');
    var storedUser = '';
    try { storedUser = localStorage.getItem(LOGIN_KEY) || ''; } catch (e) { /* empty */ }

    function updateSidebarUser(name) {
        var el = document.getElementById('sidebar-user-name');
        if (el) el.textContent = name || '';
    }

    if (storedUser) {
        if (loginOverlay) loginOverlay.classList.add('hidden');
        updateSidebarUser(storedUser);
    } else {
        document.body.style.overflow = 'hidden';
        if (loginInput) loginInput.focus();
    }

    window.doLogin = function () {
        var input = document.getElementById('login-name');
        var name = (input ? input.value : '').trim();
        if (!name) { if (input) input.focus(); return; }
        try { localStorage.setItem(LOGIN_KEY, name); } catch (e) { /* empty */ }
        var overlay = document.getElementById('login-overlay');
        if (overlay) overlay.classList.add('hidden');
        document.body.style.overflow = '';
        updateSidebarUser(name);
    };

    if (loginInput) {
        loginInput.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') window.doLogin();
        });
    }

    // ------------------------------------------------------------------
    // Sidebar toggle (mobile)
    // ------------------------------------------------------------------
    window.toggleSidebar = function () {
        var sidebar = document.getElementById('sidebar');
        var toggle = document.getElementById('sidebar-toggle');
        var overlay = document.getElementById('sidebar-overlay');
        sidebar.classList.toggle('open');
        toggle.classList.toggle('open');
        if (overlay) overlay.classList.toggle('visible');
    };

    // ------------------------------------------------------------------
    // Sidebar collapse (desktop)
    // ------------------------------------------------------------------
    var SIDEBAR_COLLAPSED_KEY = 'ecomplete_sidebar_collapsed';
    var sidebar = document.getElementById('sidebar');
    var collapseBtn = document.getElementById('sidebar-collapse-btn');

    function isSidebarCollapsed() {
        try { return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === '1'; } catch (e) { return false; }
    }

    function applySidebarState(collapsed) {
        if (!sidebar) return;
        if (collapsed) {
            sidebar.classList.add('collapsed');
            if (collapseBtn) collapseBtn.innerHTML = '&#8250;';
            if (collapseBtn) collapseBtn.title = 'Expand sidebar';
        } else {
            sidebar.classList.remove('collapsed');
            if (collapseBtn) collapseBtn.innerHTML = '&#8249;';
            if (collapseBtn) collapseBtn.title = 'Collapse sidebar';
        }
    }

    // Restore on load (desktop only)
    if (window.innerWidth > 1024) {
        applySidebarState(isSidebarCollapsed());
    }

    if (collapseBtn) {
        collapseBtn.addEventListener('click', function (e) {
            e.stopPropagation();
            var nowCollapsed = !sidebar.classList.contains('collapsed');
            applySidebarState(nowCollapsed);
            try { localStorage.setItem(SIDEBAR_COLLAPSED_KEY, nowCollapsed ? '1' : '0'); } catch (ex) { /* empty */ }
        });
    }

    // ------------------------------------------------------------------
    // Dark mode toggle
    // ------------------------------------------------------------------
    function updateThemeIcon() {
        var icon = document.getElementById('theme-icon');
        if (!icon) return;
        var isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        icon.innerHTML = isDark ? '&#9728;' : '&#9790;';
    }
    updateThemeIcon();

    window.toggleTheme = function () {
        var html = document.documentElement;
        var isDark = html.getAttribute('data-theme') === 'dark';
        if (isDark) {
            html.removeAttribute('data-theme');
            localStorage.setItem('ecomplete_theme', 'light');
        } else {
            html.setAttribute('data-theme', 'dark');
            localStorage.setItem('ecomplete_theme', 'dark');
        }
        updateThemeIcon();
        // Notify charts to re-render with new theme colors
        if (window.onThemeChange) window.onThemeChange();
    };

    // Close sidebar when a link is clicked (mobile)
    document.querySelectorAll('.sidebar-link').forEach(function (link) {
        link.addEventListener('click', function () {
            if (window.innerWidth <= 1024) {
                var sidebar = document.getElementById('sidebar');
                var toggle = document.getElementById('sidebar-toggle');
                var overlay = document.getElementById('sidebar-overlay');
                sidebar.classList.remove('open');
                toggle.classList.remove('open');
                if (overlay) overlay.classList.remove('visible');
            }
        });
    });

    // ------------------------------------------------------------------
    // Collapsible sidebar groups — persist via localStorage
    // ------------------------------------------------------------------
    var NAV_COLLAPSED_KEY = 'ecomplete_nav_collapsed';

    function getCollapsedGroups() {
        try { return JSON.parse(localStorage.getItem(NAV_COLLAPSED_KEY) || '[]'); }
        catch (e) { return []; }
    }

    function saveCollapsedGroups(groups) {
        try { localStorage.setItem(NAV_COLLAPSED_KEY, JSON.stringify(groups)); }
        catch (e) { /* empty */ }
    }

    // Restore collapsed state on load + set aria-expanded
    var collapsed = getCollapsedGroups();
    document.querySelectorAll('.sidebar-group[data-group]').forEach(function (el) {
        var groupId = el.getAttribute('data-group');
        var label = el.querySelector('.sidebar-group-label');
        if (collapsed.indexOf(groupId) !== -1) {
            el.classList.add('collapsed');
            if (label) label.setAttribute('aria-expanded', 'false');
        } else {
            if (label) label.setAttribute('aria-expanded', 'true');
        }
    });

    window.toggleNavGroup = function (groupEl) {
        if (!groupEl) return;
        var groupId = groupEl.getAttribute('data-group');
        groupEl.classList.toggle('collapsed');
        var isCollapsed = groupEl.classList.contains('collapsed');
        var label = groupEl.querySelector('.sidebar-group-label');
        if (label) label.setAttribute('aria-expanded', isCollapsed ? 'false' : 'true');
        var current = getCollapsedGroups();
        if (isCollapsed) {
            if (current.indexOf(groupId) === -1) current.push(groupId);
        } else {
            current = current.filter(function (g) { return g !== groupId; });
        }
        saveCollapsedGroups(current);
    };

    // ------------------------------------------------------------------
    // Data freshness — derive latest dates from TS data
    // ------------------------------------------------------------------
    function getLatestKey(obj) {
        if (!obj) return null;
        var keys = Object.keys(obj);
        return keys.length > 0 ? keys.sort().pop() : null;
    }

    function formatFreshness(dateStr) {
        if (!dateStr) return '--';
        var d = new Date(dateStr + 'T00:00:00');
        var now = new Date();
        var diffDays = Math.floor((now - d) / 86400000);
        var label = d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
        if (diffDays === 0) return label + ' (today)';
        if (diffDays === 1) return label + ' (1d ago)';
        return label + ' (' + diffDays + 'd ago)';
    }

    function updateFreshnessPills() {
        if (typeof TS === 'undefined') return;
        var pills = document.querySelectorAll('.freshness-pill');
        var hubDate = getLatestKey(TS.leads_by_day) || getLatestKey(TS.contacts_created_by_day);
        var monDate = getLatestKey(TS.deals_created_by_day);
        var queueDate = getLatestKey(TS.activities_by_type_by_day);
        pills.forEach(function (pill) {
            var text = pill.textContent.trim();
            if (text.indexOf('HubSpot') === 0) pill.textContent = 'HubSpot: ' + formatFreshness(hubDate);
            if (text.indexOf('Monday') === 0) pill.textContent = 'Monday: ' + formatFreshness(monDate);
            if (text.indexOf('Queue') === 0) pill.textContent = 'Queue: ' + formatFreshness(queueDate);
        });
    }

    // ------------------------------------------------------------------
    // Footer stats — populate from STATIC data
    // ------------------------------------------------------------------
    function updateFooterStats() {
        var el = document.getElementById('footer-stats');
        if (!el) return;
        if (typeof STATIC === 'undefined') { el.textContent = ''; return; }
        var parts = [];
        if (STATIC.total_contacts) parts.push('Contacts: ' + Number(STATIC.total_contacts).toLocaleString('en-GB'));
        if (STATIC.total_companies) parts.push('Companies: ' + Number(STATIC.total_companies).toLocaleString('en-GB'));
        if (STATIC.total_deals) parts.push('Deals: ' + Number(STATIC.total_deals).toLocaleString('en-GB'));
        el.textContent = parts.join(' | ');
    }

    document.addEventListener('DOMContentLoaded', function () {
        updateFreshnessPills();
        updateFooterStats();
    });
})();
