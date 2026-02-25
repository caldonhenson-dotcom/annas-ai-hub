/* ============================================================
   Connectors UI — status bar, popovers, OAuth triggers
   ============================================================ */
(function () {
    'use strict';

    function esc(s) { var d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

    // ------------------------------------------------------------------
    // Status bar (row of connector pills below stats)
    // ------------------------------------------------------------------
    function renderConnectorsBar() {
        var el = document.getElementById('connectors-bar');
        if (!el) return;
        var connectors = window.Connectors.getAll();
        el.innerHTML = '<div class="connectors-bar-label">Connectors</div>'
            + '<div class="connectors-pills">'
            + connectors.map(function (c) {
                var status = window.Connectors.getStatus(c.id);
                var dotCls = status === 'connected' ? 'dot-green'
                    : status === 'checking' ? 'dot-amber'
                    : status === 'disconnected' ? 'dot-red' : 'dot-gray';
                return '<button class="connector-pill" data-connector="' + c.id + '" '
                    + 'onclick="window.ConnectorsUI.togglePopover(\'' + c.id + '\',this)">'
                    + '<span class="connector-dot ' + dotCls + '"></span>'
                    + '<span class="connector-pill-icon">' + c.icon + '</span>'
                    + '<span class="connector-pill-name">' + esc(c.name) + '</span>'
                    + '</button>';
            }).join('')
            + '</div>';
    }

    // ------------------------------------------------------------------
    // Popover (click a connector pill)
    // ------------------------------------------------------------------
    var _activePopover = null;

    function togglePopover(connectorId, anchor) {
        closePopover();
        if (_activePopover === connectorId) { _activePopover = null; return; }
        _activePopover = connectorId;

        var c = window.Connectors.get(connectorId);
        if (!c) return;
        var status = window.Connectors.getStatus(connectorId);
        var statusLabel = status === 'connected' ? 'Connected' : status === 'checking' ? 'Checking...' : 'Disconnected';
        var statusColor = status === 'connected' ? '#16a34a' : status === 'checking' ? '#d97706' : '#ef4444';

        var pop = document.createElement('div');
        pop.className = 'connector-popover';
        pop.id = 'connector-popover';
        pop.innerHTML = '<div class="connector-pop-header">'
            + '<span style="font-size:24px">' + c.icon + '</span>'
            + '<div><div class="connector-pop-name">' + esc(c.name) + '</div>'
            + '<div class="connector-pop-status" style="color:' + statusColor + '">' + statusLabel + '</div></div></div>'
            + '<div class="connector-pop-section"><div class="connector-pop-label">Auth</div>'
            + '<div class="connector-pop-value">' + esc(c.authType) + '</div></div>'
            + '<div class="connector-pop-section"><div class="connector-pop-label">Capabilities</div>'
            + '<div class="connector-pop-caps">' + c.capabilities.map(function (cap) {
                return '<span class="connector-cap-tag">' + esc(cap) + '</span>';
            }).join('') + '</div></div>'
            + _authButton(c, status);

        var rect = anchor.getBoundingClientRect();
        pop.style.top = (rect.bottom + 8) + 'px';
        pop.style.left = Math.max(8, rect.left) + 'px';
        document.body.appendChild(pop);

        // Close on outside click
        setTimeout(function () {
            document.addEventListener('click', _outsideClick, { once: true });
        }, 10);
    }

    function _authButton(c, status) {
        if (c.authType === 'oauth' && status !== 'connected') {
            return '<button class="connector-auth-btn" onclick="window.ConnectorsUI.startOAuth(\'' + c.id + '\')">'
                + 'Connect ' + esc(c.name) + '</button>';
        }
        if (status === 'connected') {
            return '<button class="connector-recheck-btn" onclick="window.ConnectorsUI.recheck(\'' + c.id + '\')">'
                + 'Re-check</button>';
        }
        return '<div class="connector-pop-hint">Configure via environment variables</div>';
    }

    function closePopover() {
        var pop = document.getElementById('connector-popover');
        if (pop) pop.remove();
        document.removeEventListener('click', _outsideClick);
    }

    function _outsideClick(e) {
        if (!e.target.closest('.connector-popover') && !e.target.closest('.connector-pill')) {
            closePopover();
            _activePopover = null;
        }
    }

    // ------------------------------------------------------------------
    // OAuth trigger
    // ------------------------------------------------------------------
    function startOAuth(connectorId) {
        var c = window.Connectors.get(connectorId);
        if (!c || !c.authUrl) return;
        closePopover();
        _activePopover = null;
        fetch(c.authUrl + '?action=auth-url').then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.url) window.open(data.url, '_blank', 'width=600,height=700');
            })
            .catch(function () {
                if (window.Notifications) window.Notifications.show('Failed to start OAuth', 'error');
            });
    }

    function recheck(connectorId) {
        closePopover();
        _activePopover = null;
        window.Connectors.checkHealth(connectorId).then(function () { renderConnectorsBar(); });
    }

    // Listen for status changes to re-render
    window.Connectors.onStatusChange(function () { renderConnectorsBar(); });

    window.ConnectorsUI = {
        render: renderConnectorsBar,
        togglePopover: togglePopover,
        closePopover: closePopover,
        startOAuth: startOAuth,
        recheck: recheck
    };
})();
