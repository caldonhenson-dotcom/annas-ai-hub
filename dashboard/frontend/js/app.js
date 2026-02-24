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
})();
