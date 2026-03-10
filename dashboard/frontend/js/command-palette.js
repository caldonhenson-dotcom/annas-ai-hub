/* ============================================================
   Command Palette — Ctrl+K / Cmd+K quick navigation
   ============================================================ */
(function () {
    'use strict';

    var overlay = document.getElementById('cmd-overlay');
    var input = document.getElementById('cmd-input');
    var results = document.getElementById('cmd-results');
    if (!overlay || !input || !results) return;

    var activeIdx = -1;

    // Build searchable index from sidebar links
    var pages = [];
    document.querySelectorAll('.sidebar-link[data-page]').forEach(function (link) {
        var textEl = link.querySelector('.sidebar-link-text');
        var iconEl = link.querySelector('.sidebar-link-icon');
        pages.push({
            id: link.getAttribute('data-page'),
            label: textEl ? textEl.textContent.trim() : link.textContent.trim(),
            icon: iconEl ? iconEl.textContent.trim() : '',
            type: 'page'
        });
    });

    // Add actions
    var actions = [
        { id: 'toggle-dark', label: 'Toggle Dark Mode', icon: '\uD83C\uDF19', type: 'action', handler: function () { if (window.toggleTheme) window.toggleTheme(); } },
        { id: 'open-chat', label: 'Open AI Chat', icon: '\u26A1', type: 'action', handler: function () { if (window.AnnaChat) window.AnnaChat.open(); } },
        { id: 'open-settings', label: 'AI Provider Settings', icon: '\u2699', type: 'action', handler: function () { if (window.APIConfig) window.APIConfig.openSettings(); } }
    ];

    var allItems = pages.concat(actions);

    function open() {
        overlay.classList.add('open');
        input.value = '';
        activeIdx = -1;
        render(allItems);
        setTimeout(function () { input.focus(); }, 50);
    }

    function close() {
        overlay.classList.remove('open');
        input.value = '';
        activeIdx = -1;
    }

    function fuzzyMatch(query, text) {
        var q = query.toLowerCase();
        var t = text.toLowerCase();
        if (t.indexOf(q) !== -1) return true;
        var qi = 0;
        for (var ti = 0; ti < t.length && qi < q.length; ti++) {
            if (t[ti] === q[qi]) qi++;
        }
        return qi === q.length;
    }

    function filter(query) {
        if (!query) return allItems;
        return allItems.filter(function (item) {
            return fuzzyMatch(query, item.label) || fuzzyMatch(query, item.id);
        });
    }

    function render(items) {
        if (items.length === 0) {
            results.innerHTML = '<div class="cmd-empty">No results found</div>';
            return;
        }

        var html = '';
        var pageItems = items.filter(function (i) { return i.type === 'page'; });
        var actionItems = items.filter(function (i) { return i.type === 'action'; });

        if (pageItems.length) {
            html += '<div class="cmd-section-label">Pages</div>';
            pageItems.forEach(function (item, i) {
                html += '<div class="cmd-item" data-idx="' + i + '" data-id="' + item.id + '" data-type="page">' +
                    '<span class="cmd-item-icon">' + item.icon + '</span>' +
                    '<span class="cmd-item-label">' + item.label + '</span>' +
                    '</div>';
            });
        }

        if (actionItems.length) {
            html += '<div class="cmd-section-label">Actions</div>';
            actionItems.forEach(function (item, i) {
                var idx = pageItems.length + i;
                html += '<div class="cmd-item" data-idx="' + idx + '" data-id="' + item.id + '" data-type="action">' +
                    '<span class="cmd-item-icon">' + item.icon + '</span>' +
                    '<span class="cmd-item-label">' + item.label + '</span>' +
                    '</div>';
            });
        }

        results.innerHTML = html;

        // Click handlers
        results.querySelectorAll('.cmd-item').forEach(function (el) {
            el.addEventListener('click', function () {
                execute(el.getAttribute('data-id'), el.getAttribute('data-type'));
            });
        });
    }

    function execute(id, type) {
        close();
        if (type === 'page') {
            if (typeof showPage === 'function') showPage(id);
        } else if (type === 'action') {
            var action = actions.find(function (a) { return a.id === id; });
            if (action && action.handler) action.handler();
        }
    }

    function updateActive() {
        var items = results.querySelectorAll('.cmd-item');
        items.forEach(function (el, i) {
            el.classList.toggle('active', i === activeIdx);
        });
        if (items[activeIdx]) {
            items[activeIdx].scrollIntoView({ block: 'nearest' });
        }
    }

    // Input filtering
    input.addEventListener('input', function () {
        var filtered = filter(input.value.trim());
        activeIdx = filtered.length > 0 ? 0 : -1;
        render(filtered);
        updateActive();
    });

    // Keyboard navigation
    input.addEventListener('keydown', function (e) {
        var items = results.querySelectorAll('.cmd-item');
        var count = items.length;

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            activeIdx = (activeIdx + 1) % count;
            updateActive();
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            activeIdx = activeIdx <= 0 ? count - 1 : activeIdx - 1;
            updateActive();
        } else if (e.key === 'Enter') {
            e.preventDefault();
            if (activeIdx >= 0 && items[activeIdx]) {
                execute(items[activeIdx].getAttribute('data-id'), items[activeIdx].getAttribute('data-type'));
            }
        } else if (e.key === 'Escape') {
            e.preventDefault();
            close();
        }
    });

    // Click overlay to close
    overlay.addEventListener('click', function (e) {
        if (e.target === overlay) close();
    });

    // Global shortcut: Ctrl+K / Cmd+K
    document.addEventListener('keydown', function (e) {
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
            e.preventDefault();
            if (overlay.classList.contains('open')) {
                close();
            } else {
                open();
            }
        }
        // Also close on Escape if open
        if (e.key === 'Escape' && overlay.classList.contains('open')) {
            close();
        }
    });

    window.CommandPalette = { open: open, close: close };
})();
