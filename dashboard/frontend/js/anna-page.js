/* ============================================================
   Anna Page — full-page AI chat with multi-conversation
   ============================================================ */
(function () {
    'use strict';

    var AP_STORE_KEY = 'ecomplete_anna_convs';
    var apConvs = [];  // {id, title, messages:[]}
    var apActiveId = null;
    var apLoading = false;

    function apLoadConvs() {
        try { apConvs = JSON.parse(localStorage.getItem(AP_STORE_KEY) || '[]'); } catch(e) { apConvs = []; }
    }
    function apSaveConvs() {
        try { localStorage.setItem(AP_STORE_KEY, JSON.stringify(apConvs)); } catch(e) {}
    }
    function apGetActive() {
        return apConvs.find(function(c) { return c.id === apActiveId; });
    }

    function apRenderConvList() {
        var list = document.getElementById('anna-conv-list');
        if (!list) return;
        var html = '';
        for (var i = apConvs.length - 1; i >= 0; i--) {
            var c = apConvs[i];
            var active = c.id === apActiveId ? ' active' : '';
            html += '<button class="anna-conv-item' + active + '" data-cid="' + c.id + '" onclick="window.AnnaPage.switchConv(this.getAttribute(&#39;data-cid&#39;))">'
                + '<span class="conv-icon">&#128172;</span>'
                + '<span class="conv-label">' + (c.title || 'New Chat') + '</span>'
                + '<span class="conv-delete" onclick="event.stopPropagation();window.AnnaPage.deleteConv(&#39;' + c.id + '&#39;)" title="Delete">&#10005;</span>'
                + '</button>';
        }
        list.innerHTML = html;
    }

    function apRenderMessages() {
        var msgs = document.getElementById('anna-page-msgs');
        if (!msgs) return;
        var conv = apGetActive();
        msgs.innerHTML = '';
        if (!conv || conv.messages.length === 0) {
            // Show welcome
            var w = document.getElementById('anna-welcome');
            if (!w) {
                msgs.innerHTML = '<div class="anna-welcome" id="anna-welcome">'
                    + '<div class="anna-welcome-avatar">e</div>'
                    + '<div class="anna-welcome-title">eComplete AI</div>'
                    + '<div class="anna-welcome-sub">Your sales &amp; M&amp;A intelligence assistant. Ask me anything about your dashboard data.</div>'
                    + '<div class="anna-suggestions" id="anna-suggestions">'
                    + '<button class="anna-suggest-btn" onclick="window.AnnaPage.ask(this.textContent)">Summarise deal flow this month</button>'
                    + '<button class="anna-suggest-btn" onclick="window.AnnaPage.ask(this.textContent)">Which deals are stale or at risk?</button>'
                    + '<button class="anna-suggest-btn" onclick="window.AnnaPage.ask(this.textContent)">Pipeline health &amp; coverage</button>'
                    + '<button class="anna-suggest-btn" onclick="window.AnnaPage.ask(this.textContent)">Lead source effectiveness</button>'
                    + '<button class="anna-suggest-btn" onclick="window.AnnaPage.ask(this.textContent)">Top performing rep this month</button>'
                    + '<button class="anna-suggest-btn" onclick="window.AnnaPage.ask(this.textContent)">M&amp;A pipeline status</button>'
                    + '<button class="anna-suggest-btn" onclick="window.AnnaPage.ask(this.textContent)">Revenue forecast next 90 days</button>'
                    + '<button class="anna-suggest-btn" onclick="window.AnnaPage.ask(this.textContent)">Weekly summary</button>'
                    + '</div></div>';
            }
            return;
        }
        for (var i = 0; i < conv.messages.length; i++) {
            var m = conv.messages[i];
            apAddMsgDOM(m.role, m.content, m.reportTitle || null);
        }
        msgs.scrollTop = msgs.scrollHeight;
    }

    function apAddMsgDOM(role, content, reportTitle) {
        var msgs = document.getElementById('anna-page-msgs');
        if (!msgs) return;
        // Remove welcome
        var w = msgs.querySelector('.anna-welcome');
        if (w) w.remove();

        if (reportTitle) {
            // Render as branded report card
            var now = new Date();
            var dateStr = now.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
            var card = document.createElement('div');
            card.className = 'anna-report-card';
            card.innerHTML = '<div class="anna-report-card-header">'
                + '<div class="anna-report-card-dot">e</div>'
                + '<div class="anna-report-card-title">' + reportTitle + '</div>'
                + '<div class="anna-report-card-meta">eComplete AI &middot; ' + dateStr + '</div>'
                + '</div>'
                + '<div class="anna-report-card-body">' + md(content) + '</div>'
                + '<div class="anna-report-card-footer">'
                + '<button class="anna-report-action" onclick="window.AnnaPage.copyReport(this)">&#128203; Copy</button>'
                + '<button class="anna-report-action" onclick="window.AnnaPage.downloadReport(this)">&#128196; Download PDF</button>'
                + '</div>';
            card.setAttribute('data-raw', content);
            card.setAttribute('data-title', reportTitle);
            msgs.appendChild(card);
        } else {
            var div = document.createElement('div');
            div.className = 'chat-msg ' + role;
            if (role === 'assistant') {
                div.innerHTML = md(content);
                var actions = document.createElement('div');
                actions.className = 'chat-msg-actions';
                actions.style.opacity = '1';
                actions.innerHTML = '<button class="chat-action-btn" title="Copy" onclick="window.AnnaChat.copyMsg(this)">&#128203; Copy</button>';
                div.appendChild(actions);
                div.setAttribute('data-raw', content);
            } else if (role === 'user') {
                div.textContent = content;
            } else {
                div.innerHTML = content;
            }
            msgs.appendChild(div);
        }
        msgs.scrollTop = msgs.scrollHeight;
    }

    function apShowTyping() {
        var msgs = document.getElementById('anna-page-msgs');
        if (!msgs) return;
        var div = document.createElement('div');
        div.className = 'chat-typing';
        div.id = 'anna-page-typing';
        div.innerHTML = '<span></span><span></span><span></span>';
        msgs.appendChild(div);
        msgs.scrollTop = msgs.scrollHeight;
    }

    function apHideTyping() {
        var el = document.getElementById('anna-page-typing');
        if (el) el.remove();
    }

    function apEnsureConv() {
        if (!apActiveId || !apGetActive()) {
            var id = 'conv_' + Date.now();
            apConvs.push({ id: id, title: '', messages: [] });
            apActiveId = id;
            apSaveConvs();
            apRenderConvList();
        }
    }

    function apSend(text) {
        if (!text || apLoading) return;
        text = text.trim();
        if (!text) return;

        apEnsureConv();
        var conv = apGetActive();
        if (!conv) return;

        // Set title from first message
        if (!conv.title) {
            conv.title = text.length > 40 ? text.substring(0, 40) + '...' : text;
            apRenderConvList();
        }

        conv.messages.push({ role: 'user', content: text });
        apSaveConvs();
        apAddMsgDOM('user', text, null);

        var input = document.getElementById('anna-page-input');
        if (input) input.value = '';

        apLoading = true;
        apShowTyping();

        fetch(FUNC_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question: text,
                history: conv.messages.slice(-6)
            })
        })
        .then(function(r) {
            if (!r.ok) return r.json().then(function(d) { throw new Error(d.error || 'Request failed'); });
            return r.json();
        })
        .then(function(data) {
            apLoading = false;
            apHideTyping();
            var answer = data.answer || 'No response received.';
            conv.messages.push({ role: 'assistant', content: answer });
            apSaveConvs();
            apAddMsgDOM('assistant', answer, null);
        })
        .catch(function(err) {
            apLoading = false;
            apHideTyping();
            apAddMsgDOM('system', 'Error: ' + (err.message || String(err)), null);
        });
    }

    function apRunReport(reportId) {
        var prompt = REPORT_PROMPTS[reportId];
        if (!prompt || apLoading) return;
        var title = reportId.replace(/-/g, ' ').replace(/\b\w/g, function(c) { return c.toUpperCase(); });

        apEnsureConv();
        var conv = apGetActive();
        if (!conv) return;

        if (!conv.title) {
            conv.title = '📄 ' + title;
            apRenderConvList();
        }

        apLoading = true;
        apShowTyping();

        fetch(FUNC_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question: prompt,
                history: [],
                report: true
            })
        })
        .then(function(r) {
            if (!r.ok) throw new Error('Request failed (' + r.status + ')');
            return r.json();
        })
        .then(function(data) {
            apLoading = false;
            apHideTyping();
            var answer = data.answer || 'No response received.';
            conv.messages.push({ role: 'assistant', content: answer, reportTitle: title });
            apSaveConvs();
            apAddMsgDOM('assistant', answer, title);
        })
        .catch(function(err) {
            apLoading = false;
            apHideTyping();
            apAddMsgDOM('system', 'Error generating report: ' + (err.message || String(err)), null);
        });
    }

    // Init AnnaPage on load
    document.addEventListener('DOMContentLoaded', function() {
        apLoadConvs();
        if (apConvs.length > 0) {
            apActiveId = apConvs[apConvs.length - 1].id;
        }
        apRenderConvList();
        apRenderMessages();
    });

    window.AnnaPage = {
        send: function() {
            var input = document.getElementById('anna-page-input');
            if (input) apSend(input.value);
        },
        ask: function(text) {
            apSend(text);
        },
        newChat: function() {
            var id = 'conv_' + Date.now();
            apConvs.push({ id: id, title: '', messages: [] });
            apActiveId = id;
            apSaveConvs();
            apRenderConvList();
            apRenderMessages();
            var input = document.getElementById('anna-page-input');
            if (input) input.focus();
        },
        switchConv: function(cid) {
            apActiveId = cid;
            apRenderConvList();
            apRenderMessages();
        },
        deleteConv: function(cid) {
            apConvs = apConvs.filter(function(c) { return c.id !== cid; });
            if (apActiveId === cid) {
                apActiveId = apConvs.length > 0 ? apConvs[apConvs.length - 1].id : null;
            }
            apSaveConvs();
            apRenderConvList();
            apRenderMessages();
        },
        clearChat: function() {
            var conv = apGetActive();
            if (conv) {
                conv.messages = [];
                conv.title = '';
                apSaveConvs();
                apRenderConvList();
                apRenderMessages();
            }
        },
        runReport: function(reportId) {
            apRunReport(reportId);
        },
        copyReport: function(btn) {
            var card = btn.closest('.anna-report-card');
            if (!card) return;
            var raw = card.getAttribute('data-raw') || '';
            navigator.clipboard.writeText(raw).then(function() {
                var orig = btn.innerHTML;
                btn.innerHTML = '&#10003; Copied';
                setTimeout(function() { btn.innerHTML = orig; }, 1500);
            });
        },
        downloadReport: function(btn) {
            var card = btn.closest('.anna-report-card');
            if (!card) return;
            var raw = card.getAttribute('data-raw') || '';
            var title = card.getAttribute('data-title') || 'Report';
            openPrintWindow(title, md(raw));
        }
    };

        })();
})();
