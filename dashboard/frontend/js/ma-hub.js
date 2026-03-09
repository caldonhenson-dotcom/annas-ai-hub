/* ============================================================
   M&A Hub — tab switching + content rendering
   Legacy Monday.com pages removed — content now renders inline
   ============================================================ */
(function () {
    'use strict';

    var loaded = {};

    window.switchMATab = function (tabKey) {
        // Update tab buttons
        var tabs = document.getElementById('ma-hub-tabs');
        if (tabs) {
            tabs.querySelectorAll('.ma-hub-tab').forEach(function (btn) {
                btn.classList.toggle('active', btn.getAttribute('data-matab') === tabKey);
            });
        }

        // Show/hide panels
        document.querySelectorAll('.ma-hub-panel').forEach(function (p) {
            p.classList.remove('active');
        });
        var panel = document.getElementById('ma-panel-' + tabKey);
        if (panel) panel.classList.add('active');
    };

    // Render M&A Hub when page loads
    window.renderMAHub = function () {
        // Pipeline and IC content will be rendered inline in Phase 3
        // For now, the HTML skeleton in ma-hub.html provides the structure
    };
})();
