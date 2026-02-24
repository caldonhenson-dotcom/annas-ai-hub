/* ============================================================
   Outreach Actions — LinkedIn auth, extension bridge
   ============================================================ */
(function () {
    'use strict';

    window.LinkedInAuth = {
        _connected: false,
        _profile: null,
        _extensionReady: false,

        // Called from the main "Connect LinkedIn" button in the bot panel
        // If extension is ready, does single-click without opening modal
        // If already connected, opens modal to show status / disconnect
        quickConnect: function() {
            if (this._connected) {
                this.open();
                return;
            }
            if (LI_EXTENSION_ID) {
                // Single-click: skip the modal entirely
                var mainBtn = document.getElementById('li-connect-btn-main');
                if (mainBtn) {
                    mainBtn.disabled = true;
                    mainBtn.innerHTML = '<span class="loading-spinner" style="vertical-align:middle;border-width:2px;width:12px;height:12px"></span> Connecting...';
                }
                var self = this;
                chrome.runtime.sendMessage(LI_EXTENSION_ID, { action: 'GET_LINKEDIN_COOKIES' }, function(response) {
                    if (chrome.runtime.lastError || !response || !response.success) {
                        if (mainBtn) { mainBtn.disabled = false; mainBtn.innerHTML = '&#128279; Connect LinkedIn'; }
                        self.open(); // Fall back to modal
                        return;
                    }
                    self._authenticate(response.li_at, response.csrf_token, function(ok, data) {
                        if (mainBtn) mainBtn.disabled = false;
                        if (ok) {
                            // Done! Button updates via _updateUI
                        } else {
                            if (mainBtn) mainBtn.innerHTML = '&#128279; Connect LinkedIn';
                            self.open();
                            self._showMsg(data.error || 'Connection failed', 'error');
                        }
                    });
                });
            } else {
                this.open();
            }
        },

        open: function() {
            document.getElementById('linkedin-auth-overlay').classList.remove('hidden');
            this.checkStatus();
            this._detectExtension();
        },

        close: function() {
            document.getElementById('linkedin-auth-overlay').classList.add('hidden');
        },

        // ── Single-click flow ──────────────────────────────
        oneClick: function() {
            var btn = document.getElementById('li-oneclick-btn');
            var label = document.getElementById('li-oneclick-label');
            var status = document.getElementById('li-oneclick-status');
            var self = this;

            // If extension is detected, use it
            if (LI_EXTENSION_ID) {
                label.innerHTML = '<span class="loading-spinner" style="vertical-align:middle;border-width:2px;width:14px;height:14px"></span> Connecting...';
                btn.disabled = true;
                status.textContent = 'Reading LinkedIn cookies via extension...';

                chrome.runtime.sendMessage(
                    LI_EXTENSION_ID,
                    { action: 'GET_LINKEDIN_COOKIES' },
                    function(response) {
                        if (chrome.runtime.lastError) {
                            label.innerHTML = '&#128279; Connect My LinkedIn';
                            btn.disabled = false;
                            status.textContent = '';
                            self._showExtInstall('Extension communication error. Reinstall or reload the extension.');
                            return;
                        }
                        if (!response || !response.success) {
                            label.innerHTML = '&#128279; Connect My LinkedIn';
                            btn.disabled = false;
                            status.textContent = '';
                            self._showMsg(response ? response.error : 'No response from extension', 'error');
                            return;
                        }

                        // Got cookies — now validate via our API
                        status.textContent = 'Validating with LinkedIn...';
                        self._authenticate(response.li_at, response.csrf_token, function(ok, data) {
                            label.innerHTML = '&#128279; Connect My LinkedIn';
                            btn.disabled = false;
                            status.textContent = '';
                            if (ok) {
                                self._showMsg('Connected as ' + data.display_name, 'success');
                            } else {
                                self._showMsg(data.error || 'Connection failed', 'error');
                            }
                        });
                    }
                );
            } else {
                // No extension — show install instructions
                this._showExtInstall();
            }
        },

        retryExtension: function() {
            var self = this;
            this._detectExtension(function(found) {
                if (found) {
                    document.getElementById('li-ext-install').style.display = 'none';
                    self._showMsg('Extension detected! Click the button above to connect.', 'success');
                } else {
                    self._showMsg('Extension not detected yet. Make sure it is loaded and enabled.', 'error');
                }
            });
        },

        // ── Extension detection ────────────────────────────
        _detectExtension: function(callback) {
            var self = this;

            // Already have the ID from content script broadcast
            if (LI_EXTENSION_ID) {
                self._extensionReady = true;
                var installArea = document.getElementById('li-ext-install');
                if (installArea) installArea.style.display = 'none';
                if (callback) callback(true);
                return;
            }

            // Check localStorage for previously-saved ID
            var savedId = localStorage.getItem('li_ext_id');
            if (savedId && typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.sendMessage) {
                try {
                    chrome.runtime.sendMessage(savedId, { action: 'GET_LINKEDIN_COOKIES' }, function(resp) {
                        if (!chrome.runtime.lastError && resp) {
                            LI_EXTENSION_ID = savedId;
                            self._extensionReady = true;
                            var installArea = document.getElementById('li-ext-install');
                            if (installArea) installArea.style.display = 'none';
                            if (callback) callback(true);
                        } else {
                            self._extensionReady = false;
                            if (callback) callback(false);
                        }
                    });
                    return;
                } catch(e) { /* fall through */ }
            }

            // Send a ping in case the content script is ready but we missed it
            window.postMessage({ type: 'ANNAS_LI_EXT_PING' }, '*');

            // Wait briefly for a response
            var timeout = setTimeout(function() {
                self._extensionReady = false;
                if (callback) callback(false);
            }, 500);

            var handler = function(event) {
                if (event.data && event.data.type === 'ANNAS_LI_EXT_READY' && event.data.extensionId) {
                    clearTimeout(timeout);
                    window.removeEventListener('message', handler);
                    LI_EXTENSION_ID = event.data.extensionId;
                    localStorage.setItem('li_ext_id', LI_EXTENSION_ID);
                    self._extensionReady = true;
                    var installArea = document.getElementById('li-ext-install');
                    if (installArea) installArea.style.display = 'none';
                    if (callback) callback(true);
                }
            };
            window.addEventListener('message', handler);
        },

        _showExtInstall: function(customMsg) {
            var area = document.getElementById('li-ext-install');
            if (area) area.style.display = '';
            if (customMsg) this._showMsg(customMsg, 'error');
        },

        // ── Core authenticate call ─────────────────────────
        _authenticate: function(liAt, csrfToken, callback) {
            var self = this;
            fetch(API.session, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ li_at: liAt, csrf_token: csrfToken })
            })
            .then(function(r) { return r.json().then(function(d) { return { ok: r.ok, data: d }; }); })
            .then(function(res) {
                if (res.ok && res.data.authenticated) {
                    self._connected = true;
                    self._profile = res.data;
                    self._updateUI(res.data);
                    callback(true, res.data);
                } else {
                    callback(false, res.data);
                }
            })
            .catch(function(e) {
                callback(false, { error: 'Network error: ' + e.message });
            });
        },

        // ── Manual fallback ────────────────────────────────
        submit: function() {
            var liAt = document.getElementById('li-input-li_at').value.trim();
            var csrf = document.getElementById('li-input-csrf').value.trim().replace(/"/g, '');
            if (!liAt || liAt.length < 50) { this._showMsg('li_at cookie must be at least 50 characters', 'error'); return; }
            if (!csrf || csrf.length < 10) { this._showMsg('JSESSIONID must be at least 10 characters', 'error'); return; }

            var btn = document.getElementById('li-submit-btn');
            btn.disabled = true;
            btn.innerHTML = '<span class="loading-spinner"></span> Validating...';
            var self = this;

            this._authenticate(liAt, csrf, function(ok, data) {
                btn.disabled = false;
                btn.textContent = 'Connect & Validate';
                if (ok) {
                    self._showMsg('Connected as ' + data.display_name, 'success');
                    document.getElementById('li-input-li_at').value = '';
                    document.getElementById('li-input-csrf').value = '';
                } else {
                    self._showMsg(data.error || 'Connection failed', 'error');
                }
            });
        },

        // ── Status & session management ────────────────────
        checkStatus: function() {
            var self = this;
            fetch(API.session)
                .then(function(r) { return r.json(); })
                .then(function(d) {
                    self._connected = d.authenticated;
                    self._profile = d.authenticated ? d : null;
                    self._updateUI(d);
                })
                .catch(function() {
                    self._updateUI({ authenticated: false });
                });
        },

        disconnect: function() {
            var self = this;
            fetch(API.session, { method: 'DELETE' })
                .then(function() {
                    self._connected = false;
                    self._profile = null;
                    self._updateUI({ authenticated: false });
                    self._showMsg('Disconnected', 'success');
                })
                .catch(function() {
                    self._showMsg('Disconnect failed — try again', 'error');
                });
        },

        _updateUI: function(data) {
            var box = document.getElementById('li-status-box');
            var text = document.getElementById('li-status-text');
            var detail = document.getElementById('li-status-detail');
            var methods = document.getElementById('li-auth-methods');
            var disconnect = document.getElementById('li-disconnect-section');
            var mainBtn = document.getElementById('li-connect-btn-main');

            if (data.authenticated) {
                box.className = 'li-status-connected';
                box.querySelector('span').innerHTML = '&#9989;';
                text.textContent = 'Connected as ' + (data.display_name || 'Unknown');
                detail.textContent = 'Session valid' + (data.expires_at ? ' until ' + new Date(data.expires_at).toLocaleDateString() : '');
                methods.style.display = 'none';
                disconnect.style.display = '';
                if (mainBtn) mainBtn.innerHTML = '&#9989; ' + escHtml(data.display_name || 'Connected');

                var botArea = document.getElementById('bot-controls-area');
                if (botArea) botArea.style.display = '';
                var connAs = document.getElementById('bot-connected-as');
                if (connAs) connAs.textContent = 'as ' + (data.display_name || '');

                var sendBtn = document.getElementById('pp-send-btn');
                if (sendBtn) sendBtn.style.display = '';
            } else {
                box.className = 'li-status-disconnected';
                box.querySelector('span').innerHTML = '&#128274;';
                text.textContent = 'Not connected';
                detail.textContent = 'Connect your LinkedIn to enable outreach';
                methods.style.display = '';
                disconnect.style.display = 'none';
                if (mainBtn) mainBtn.innerHTML = '&#128279; Connect LinkedIn';

                var botArea2 = document.getElementById('bot-controls-area');
                if (botArea2) botArea2.style.display = 'none';
            }
        },

        _showMsg: function(msg, type) {
            var el = document.getElementById('li-auth-message');
            el.style.display = '';
            el.style.background = type === 'success' ? '#ecfdf5' : '#fef2f2';
            el.style.color = type === 'success' ? '#059669' : '#dc2626';
            el.textContent = msg;
            setTimeout(function() { el.style.display = 'none'; }, 5000);
        }
    };

    // Check session on page load
    window.LinkedInAuth.checkStatus();

    // Listen for Chrome extension broadcasting its ID (content script)
    window.addEventListener('message', function(event) {
        if (event.data && event.data.type === 'ANNAS_LI_EXT_READY' && event.data.extensionId) {
            LI_EXTENSION_ID = event.data.extensionId;
            localStorage.setItem('li_ext_id', event.data.extensionId);
            window.LinkedInAuth._extensionReady = true;
        }
    });

    // ══════════════════════════════════════════════════════
    // PROSPECT DETAIL PANEL
    // ══════════════════════════════════════════════════════
})();
