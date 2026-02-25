/* ============================================================
   M&A Hub — tab switching + lazy content loading
   ============================================================ */
(function () {
    'use strict';

    var loaded = { pipeline: false, ic: false };
    var PAGE_MAP = {
        pipeline: { src: 'pages/monday-pipeline.html', scripts: ['js/monday-pipeline.js'] },
        ic: { src: 'pages/monday-ic.html', scripts: ['js/monday-ic.js'] }
    };

    function loadTabContent(tabKey) {
        if (loaded[tabKey]) return Promise.resolve();
        var panel = document.getElementById('ma-panel-' + tabKey);
        if (!panel) return Promise.resolve();
        var cfg = PAGE_MAP[tabKey];
        if (!cfg) return Promise.resolve();

        return fetch(cfg.src)
            .then(function (r) {
                if (!r.ok) throw new Error('Failed to load ' + tabKey);
                return r.text();
            })
            .then(function (html) {
                panel.innerHTML = html;
                loaded[tabKey] = true;
                // Load scripts sequentially
                return cfg.scripts.reduce(function (chain, src) {
                    return chain.then(function () {
                        return new Promise(function (resolve, reject) {
                            // Skip if already loaded globally
                            var existing = document.querySelector('script[src="' + src + '"]');
                            if (existing) { resolve(); return; }
                            var s = document.createElement('script');
                            s.src = src;
                            s.onload = resolve;
                            s.onerror = reject;
                            document.body.appendChild(s);
                        });
                    });
                }, Promise.resolve());
            })
            .catch(function () {
                panel.innerHTML = '<div style="padding:40px;text-align:center;color:var(--text-muted)">'
                    + '<div style="font-size:32px;margin-bottom:8px">&#9888;</div>'
                    + '<div style="font-weight:600">Failed to load content</div></div>';
            });
    }

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

        // Lazy-load content on first switch
        loadTabContent(tabKey);
    };

    // Auto-load pipeline tab when M&A Hub page renders
    window.renderMAHub = function () {
        loadTabContent('pipeline');
    };
})();
