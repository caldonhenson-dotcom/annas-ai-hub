/* ============================================================
   Notifications — bell, alerts, data freshness, quick actions
   ============================================================ */
(function () {
    'use strict';

    var NOTIF_KEY = 'ecomplete_notifications';
    var DISMISSED_KEY = 'ecomplete_notif_dismissed';
    var panelOpen = false;

    // ------------------------------------------------------------------
    // Notification storage
    // ------------------------------------------------------------------
    function loadNotifs() {
        try { return JSON.parse(localStorage.getItem(NOTIF_KEY) || '[]'); }
        catch (e) { return []; }
    }

    function saveNotifs(notifs) {
        try { localStorage.setItem(NOTIF_KEY, JSON.stringify(notifs)); }
        catch (e) { /* empty */ }
    }

    function getDismissed() {
        try { return JSON.parse(localStorage.getItem(DISMISSED_KEY) || '[]'); }
        catch (e) { return []; }
    }

    function addDismissed(id) {
        var d = getDismissed();
        if (d.indexOf(id) === -1) d.push(id);
        if (d.length > 100) d = d.slice(-100);
        try { localStorage.setItem(DISMISSED_KEY, JSON.stringify(d)); }
        catch (e) { /* empty */ }
    }

    // ------------------------------------------------------------------
    // Generate notifications from dashboard state
    // ------------------------------------------------------------------
    function generateNotifications() {
        var notifs = [];
        var now = new Date();
        var today = now.toISOString().split('T')[0];
        var dismissed = getDismissed();

        // Data freshness alerts
        var freshPills = document.querySelectorAll('.freshness-pill');
        freshPills.forEach(function (pill) {
            var text = pill.textContent.trim();
            if (text.indexOf('--') !== -1) {
                var source = text.split(':')[0].trim();
                var id = 'fresh-' + source.toLowerCase().replace(/\s/g, '-');
                if (dismissed.indexOf(id) === -1) {
                    notifs.push({
                        id: id, type: 'warning', icon: '&#9888;',
                        title: source + ' data unavailable',
                        desc: 'No sync data detected. Check integration.',
                        action: null, time: today
                    });
                }
            }
        });

        // Pipeline alerts from static data
        if (window.STATIC && window.STATIC.PIPELINE_DEALS) {
            var staleDeals = window.STATIC.PIPELINE_DEALS.filter(function (d) {
                if (!d.closeDate) return false;
                var closeDate = new Date(d.closeDate);
                return closeDate < now && d.stage !== 'Closed Won' && d.stage !== 'Closed Lost';
            });
            if (staleDeals.length > 0) {
                var staleId = 'stale-deals-' + today;
                if (dismissed.indexOf(staleId) === -1) {
                    notifs.push({
                        id: staleId, type: 'danger', icon: '&#128680;',
                        title: staleDeals.length + ' overdue deal' + (staleDeals.length > 1 ? 's' : ''),
                        desc: 'Deals past expected close date need attention.',
                        action: { label: 'View Pipeline', page: 'pipeline' },
                        time: today
                    });
                }
            }
        }

        // Token usage alert (if Claude)
        if (window.APIConfig && window.APIConfig.getProvider() === 'claude') {
            var usage = null;
            try { usage = JSON.parse(localStorage.getItem('ecomplete_token_usage') || '{}'); }
            catch (e) { /* empty */ }
            if (usage && usage.cost > 1) {
                var costId = 'cost-warn-' + today;
                if (dismissed.indexOf(costId) === -1) {
                    notifs.push({
                        id: costId, type: 'info', icon: '&#128176;',
                        title: 'API spend: $' + usage.cost.toFixed(2),
                        desc: 'Total Claude API cost. Consider switching to Groq for free queries.',
                        action: { label: 'Settings', openSettings: true },
                        time: today
                    });
                }
            }
        }

        // AI Memory reminder
        if (window.AIMemory) {
            var mem = window.AIMemory.getMemory();
            var stats = null;
            try { stats = JSON.parse(localStorage.getItem('ecomplete_ai_stats') || '{}'); }
            catch (e) { /* empty */ }
            if (stats && stats.totalQuestions > 10 && mem.notes.length === 0) {
                var memId = 'memory-tip';
                if (dismissed.indexOf(memId) === -1) {
                    notifs.push({
                        id: memId, type: 'info', icon: '&#129504;',
                        title: 'Tip: Add memory notes',
                        desc: 'You\'ve asked ' + stats.totalQuestions + ' questions. Add notes to Anna for better context.',
                        action: { label: 'Open Anna', page: 'anna' },
                        time: today
                    });
                }
            }
        }

        saveNotifs(notifs);
        return notifs;
    }

    // ------------------------------------------------------------------
    // Badge count
    // ------------------------------------------------------------------
    function updateBadge() {
        var badge = document.getElementById('notif-badge');
        if (!badge) return;
        var notifs = loadNotifs();
        var count = notifs.length;
        if (count > 0) {
            badge.textContent = count > 9 ? '9+' : String(count);
            badge.style.display = '';
        } else {
            badge.style.display = 'none';
        }
    }

    // ------------------------------------------------------------------
    // Notification panel UI
    // ------------------------------------------------------------------
    function renderPanel() {
        var container = document.getElementById('notif-panel');
        if (!container) createPanel();
        container = document.getElementById('notif-panel');
        if (!container) return;

        var notifs = loadNotifs();
        var html = '<div class="notif-panel-header">'
            + '<span class="notif-panel-title">Notifications</span>'
            + '<button class="notif-panel-close" onclick="window.Notifications.close()">&#10005;</button>'
            + '</div>';

        if (notifs.length === 0) {
            html += '<div class="notif-panel-empty">&#10003; All clear! No alerts right now.</div>';
        } else {
            notifs.forEach(function (n) {
                html += '<div class="notif-item notif-' + n.type + '">'
                    + '<div class="notif-item-icon">' + n.icon + '</div>'
                    + '<div class="notif-item-body">'
                    + '<div class="notif-item-title">' + n.title + '</div>'
                    + '<div class="notif-item-desc">' + n.desc + '</div>';
                if (n.action) {
                    if (n.action.page) {
                        html += '<button class="notif-action-btn" onclick="window.showPage(\'' + n.action.page + '\');window.Notifications.dismiss(\'' + n.id + '\')">'
                            + n.action.label + '</button>';
                    } else if (n.action.openSettings) {
                        html += '<button class="notif-action-btn" onclick="window.APIConfig&&window.APIConfig.openSettings();window.Notifications.dismiss(\'' + n.id + '\')">'
                            + n.action.label + '</button>';
                    }
                }
                html += '</div>'
                    + '<button class="notif-dismiss" onclick="window.Notifications.dismiss(\'' + n.id + '\')" title="Dismiss">&#10005;</button>'
                    + '</div>';
            });
        }

        container.innerHTML = html;
        container.classList.toggle('open', panelOpen);
    }

    function createPanel() {
        var panel = document.createElement('div');
        panel.id = 'notif-panel';
        panel.className = 'notif-panel';
        document.body.appendChild(panel);
    }

    function open() {
        panelOpen = true;
        generateNotifications();
        renderPanel();
        updateBadge();
    }

    function close() {
        panelOpen = false;
        var panel = document.getElementById('notif-panel');
        if (panel) panel.classList.remove('open');
    }

    function dismiss(id) {
        addDismissed(id);
        var notifs = loadNotifs().filter(function (n) { return n.id !== id; });
        saveNotifs(notifs);
        renderPanel();
        updateBadge();
    }

    // ------------------------------------------------------------------
    // Init — generate on load, refresh every 5 minutes
    // ------------------------------------------------------------------
    document.addEventListener('DOMContentLoaded', function () {
        var bell = document.getElementById('notif-bell');
        if (bell) {
            bell.addEventListener('click', function () {
                if (panelOpen) close(); else open();
            });
        }
        // Close on outside click
        document.addEventListener('click', function (e) {
            if (!panelOpen) return;
            var panel = document.getElementById('notif-panel');
            var bell = document.getElementById('notif-bell');
            if (panel && !panel.contains(e.target) && bell && !bell.contains(e.target)) {
                close();
            }
        });

        // Initial generation
        setTimeout(function () {
            generateNotifications();
            updateBadge();
        }, 2000);

        // Refresh periodically
        setInterval(function () {
            generateNotifications();
            updateBadge();
        }, 300000);
    });

    window.Notifications = { open: open, close: close, dismiss: dismiss, refresh: function () { generateNotifications(); updateBadge(); } };
})();
