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

    // Restore collapsed state on load
    var collapsed = getCollapsedGroups();
    collapsed.forEach(function (groupId) {
        var el = document.querySelector('.sidebar-group[data-group="' + groupId + '"]');
        if (el) el.classList.add('collapsed');
    });

    window.toggleNavGroup = function (groupEl) {
        if (!groupEl) return;
        var groupId = groupEl.getAttribute('data-group');
        groupEl.classList.toggle('collapsed');
        var current = getCollapsedGroups();
        if (groupEl.classList.contains('collapsed')) {
            if (current.indexOf(groupId) === -1) current.push(groupId);
        } else {
            current = current.filter(function (g) { return g !== groupId; });
        }
        saveCollapsedGroups(current);
    };
})();
