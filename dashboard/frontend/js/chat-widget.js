/* ============================================================
   Chat Widget — FAB popup, messaging, reports, keyboard shortcut
   ============================================================ */
(function () {
    'use strict';

    var FUNC_URL = '/api/ai-query';
    var md = window.md;
    var escHtml = window.escHtml;
    var history = [];
    var isOpen = false;
    var isLoading = false;

    var REPORT_PROMPTS = {
        'monthly-deal-flow': 'Generate a comprehensive Monthly Deal Flow Summary report. Include: total deals created vs closed this period, won vs lost breakdown with values in GBP, new pipeline added, average deal size, deal velocity, and comparison to prior period. Format with clear sections using headings and tables where appropriate.',
        'pipeline-health': 'Generate a Pipeline Health Report. Include: total pipeline value and weighted value in GBP, pipeline coverage ratio, stage-by-stage breakdown with deal counts and values, average time in each stage, stale deals requiring attention, and overall pipeline risk assessment. Use headings and bullet points.',
        'lead-source': 'Generate a Lead Source Analysis report. Include: total leads by source with counts, lead-to-MQL and MQL-to-SQL conversion rates by source, most effective channels, trend analysis, and recommendations for lead generation improvement. Format with clear sections.',
        'weekly-activity': 'Generate a Weekly Activity Report. Include: total activities (calls, emails, meetings, tasks, notes) by rep, activity-to-deal ratios, most active reps, engagement trends, and touches per won deal analysis. Format as a structured report with tables.',
        'ma-pipeline': 'Generate an M&A Pipeline Status report. Include: total active projects, stage distribution breakdown, stale projects requiring attention with days stale, owner workload summary, IC scorecard highlights, and upcoming decision points. Use clear headings.',
        'rep-scorecard': 'Generate a Rep Performance Scorecard. For each sales rep, include: deals owned (count and value in GBP), win rate, activity volume breakdown, average deal size, pipeline contribution, and relative performance. Format as a comparative table or structured list.'
    };

    // Expose for anna-page.js (separate IIFE needs global access)
    window.FUNC_URL = FUNC_URL;
    window.REPORT_PROMPTS = REPORT_PROMPTS;

    function $(id) { return document.getElementById(id); }

    // ---- Add message to chat ----
    function addMessage(role, content) {
        var msgs = $('chat-messages');
        if (!msgs) return;
        var div = document.createElement('div');
        div.className = 'chat-msg ' + role;
        if (role === 'assistant') {
            div.innerHTML = md(content);
            // Action bar: copy + export
            var actions = document.createElement('div');
            actions.className = 'chat-msg-actions';
            actions.innerHTML = '<button class="chat-action-btn" title="Copy to clipboard" onclick="window.AnnaChat.copyMsg(this)">&#128203; Copy</button>'
                + '<button class="chat-action-btn" title="Export as PDF" onclick="window.AnnaChat.exportMsg(this)">&#128196; Export</button>';
            div.appendChild(actions);
            div.setAttribute('data-raw', content);
        } else {
            div.textContent = content;
        }
        msgs.appendChild(div);
        msgs.scrollTop = msgs.scrollHeight;
    }

    function showTyping() {
        var msgs = $('chat-messages');
        if (!msgs) return;
        var div = document.createElement('div');
        div.className = 'chat-typing';
        div.id = 'chat-typing';
        div.innerHTML = '<span></span><span></span><span></span>';
        msgs.appendChild(div);
        msgs.scrollTop = msgs.scrollHeight;
    }

    function hideTyping() {
        var el = $('chat-typing');
        if (el) el.remove();
    }

    function setLoading(loading) {
        isLoading = loading;
        var btn = $('chat-send');
        var input = $('chat-input');
        if (btn) btn.disabled = loading;
        if (input) input.disabled = loading;
        if (loading) showTyping(); else hideTyping();
    }

    // ---- Send message ----
    function sendMessage(text) {
        if (!text || isLoading) return;
        text = text.trim();
        if (!text) return;

        // Track for self-learning
        if (window.AIMemory) window.AIMemory.trackQuestion(text);

        // Hide suggestions after first message
        var suggestions = $('chat-suggestions');
        if (suggestions) suggestions.style.display = 'none';

        addMessage('user', text);
        history.push({ role: 'user', content: text });

        var input = $('chat-input');
        if (input) input.value = '';

        setLoading(true);

        var endpoint = window.getApiEndpoint ? window.getApiEndpoint() : FUNC_URL;
        var payload = window.buildPayload ? window.buildPayload(text, history.slice(-6)) : { question: text, history: history.slice(-6) };

        fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
        .then(function(r) {
            if (!r.ok) {
                return r.json().then(function(d) {
                    throw new Error(d.error || 'Request failed (' + r.status + ')');
                });
            }
            return r.json();
        })
        .then(function(data) {
            setLoading(false);
            var answer = data.answer || 'No response received.';
            addMessage('assistant', answer);
            history.push({ role: 'assistant', content: answer });
            // Track Claude token usage
            if (data.usage && window.APIConfig) {
                window.APIConfig.addTokens(data.usage.input_tokens || 0, data.usage.output_tokens || 0);
            }
        })
        .catch(function(err) {
            setLoading(false);
            var msg = err.message || String(err);
            if (msg.indexOf('Failed to fetch') !== -1 || msg.indexOf('NetworkError') !== -1) {
                msg = 'Cannot reach the AI service. Please try again in a moment.';
            }
            addMessage('system', 'Error: ' + msg);
        });
    }

    // ---- Public API ----
    window.AnnaChat = {
        open: function() {
            var panel = $('chat-panel');
            var fab = $('chat-fab');
            if (panel) panel.classList.add('open');
            if (fab) fab.classList.add('has-panel');
            isOpen = true;
            var input = $('chat-input');
            if (input) setTimeout(function() { input.focus(); }, 100);
        },
        close: function() {
            var panel = $('chat-panel');
            var fab = $('chat-fab');
            if (panel) panel.classList.remove('open');
            if (fab) fab.classList.remove('has-panel');
            isOpen = false;
        },
        send: function() {
            var input = $('chat-input');
            if (input) sendMessage(input.value);
        },
        ask: function(text) {
            sendMessage(text);
        },
        toggleGroup: function(headerEl) {
            var group = headerEl.parentElement;
            if (group) group.classList.toggle('collapsed');
        },
        switchTab: function(tab) {
            var chatMsgs = $('chat-messages');
            var chatSuggestions = $('chat-suggestions');
            var reports = $('chat-reports');
            var inputArea = $('chat-input-area');
            var tabs = document.querySelectorAll('.chat-tab');
            for (var i = 0; i < tabs.length; i++) {
                if (tabs[i].getAttribute('data-tab') === tab) {
                    tabs[i].classList.add('active');
                } else {
                    tabs[i].classList.remove('active');
                }
            }
            if (tab === 'chat') {
                if (chatMsgs) chatMsgs.style.display = '';
                if (chatSuggestions && history.length === 0) chatSuggestions.style.display = '';
                if (reports) reports.style.display = 'none';
                if (inputArea) inputArea.style.display = '';
            } else {
                if (chatMsgs) chatMsgs.style.display = 'none';
                if (chatSuggestions) chatSuggestions.style.display = 'none';
                if (reports) reports.style.display = '';
                if (inputArea) inputArea.style.display = 'none';
            }
        },
        copyMsg: function(btn) {
            var msgDiv = btn.closest('.chat-msg');
            if (!msgDiv) return;
            var raw = msgDiv.getAttribute('data-raw') || msgDiv.textContent;
            navigator.clipboard.writeText(raw).then(function() {
                var orig = btn.innerHTML;
                btn.innerHTML = '&#10003; Copied';
                setTimeout(function() { btn.innerHTML = orig; }, 1500);
            });
        },
        exportMsg: function(btn) {
            var msgDiv = btn.closest('.chat-msg');
            if (!msgDiv) return;
            var raw = msgDiv.getAttribute('data-raw') || '';
            openPrintWindow('eComplete AI Response', md(raw));
        },
        runReport: function(reportId) {
            var prompt = REPORT_PROMPTS[reportId];
            if (!prompt) return;
            // Open window immediately in click context to avoid popup blocker
            var w = window.open('', '_blank');
            if (!w) { showToast('Please allow pop-ups to export reports', 'error'); return; }
            w.document.write('<!DOCTYPE html><html><head><title>Generating Report...</title>'
                + '<link href="https://fonts.googleapis.com/css2?family=Assistant:wght@400;600;700;800&display=swap" rel="stylesheet">'
                + '<style>body{font-family:"Assistant",sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;color:#6b7280;margin:0;}</style>'
                + '</head><body><div style="text-align:center"><div style="font-size:24px;margin-bottom:8px">&#9889; Generating report...</div>'
                + '<div>This may take a few seconds</div></div></body></html>');
            w.document.close();

            var title = reportId.replace(/-/g, ' ').replace(/\b\w/g, function(c) { return c.toUpperCase(); });

            var rptEndpoint = window.getApiEndpoint ? window.getApiEndpoint() : FUNC_URL;
            var rptPayload = window.buildPayload ? window.buildPayload(prompt, [], { report: true }) : { question: prompt, history: [], report: true };

            fetch(rptEndpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(rptPayload)
            })
            .then(function(r) {
                if (!r.ok) throw new Error('Request failed (' + r.status + ')');
                return r.json();
            })
            .then(function(data) {
                var answer = data.answer || 'No response received.';
                if (data.usage && window.APIConfig) {
                    window.APIConfig.addTokens(data.usage.input_tokens || 0, data.usage.output_tokens || 0);
                }
                var now = new Date();
                var dateStr = now.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
                var timeStr = now.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
                w.document.open();
                w.document.write('<!DOCTYPE html><html><head>'
                    + '<meta charset="UTF-8"><title>' + title + '</title>'
                    + '<link href="https://fonts.googleapis.com/css2?family=Assistant:wght@400;600;700;800&display=swap" rel="stylesheet">'
                    + '<style>'
                    + 'body { font-family: "Assistant", sans-serif; color: #121212; margin: 0; padding: 40px; line-height: 1.6; }'
                    + '.rpt-header { border-bottom: 3px solid #3CB4AD; padding-bottom: 16px; margin-bottom: 24px; }'
                    + '.rpt-brand { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }'
                    + '.rpt-dot { width: 28px; height: 28px; border-radius: 50%; background: #3CB4AD; display: flex; align-items: center; justify-content: center; font-size: 14px; font-weight: 800; color: #fff; }'
                    + '.rpt-name { font-size: 18px; font-weight: 800; color: #242833; }'
                    + '.rpt-title { font-size: 22px; font-weight: 700; color: #242833; margin: 8px 0 4px; }'
                    + '.rpt-meta { font-size: 12px; color: #6b7280; }'
                    + '.rpt-body { font-size: 14px; }'
                    + '.rpt-body strong { font-weight: 700; }'
                    + '.rpt-body ul, .rpt-body ol { margin: 8px 0; padding-left: 24px; }'
                    + '.rpt-body li { margin-bottom: 4px; }'
                    + '.rpt-body code { background: #f3f4f6; padding: 2px 5px; border-radius: 3px; font-size: 13px; }'
                    + '.rpt-footer { margin-top: 40px; padding-top: 16px; border-top: 1px solid #e2e5ea; font-size: 11px; color: #6b7280; text-align: center; }'
                    + '@media print { body { padding: 20px; } }'
                    + '</style></head><body>'
                    + '<div class="rpt-header">'
                    + '<div class="rpt-brand"><div class="rpt-dot">e</div><span class="rpt-name">eComplete</span></div>'
                    + '<div class="rpt-title">' + title + '</div>'
                    + '<div class="rpt-meta">Generated by eComplete AI &middot; ' + dateStr + ' at ' + timeStr + '</div>'
                    + '</div>'
                    + '<div class="rpt-body">' + md(answer) + '</div>'
                    + '<div class="rpt-footer">eComplete &mdash; Sales &amp; M&amp;A Intelligence Dashboard &middot; Confidential</div>'
                    + '<scr' + 'ipt>window.onload=function(){ window.print(); }</scr' + 'ipt>'
                    + '</body></html>');
                w.document.close();
            })
            .catch(function(err) {
                w.document.open();
                w.document.write('<html><body style="font-family:Assistant,sans-serif;padding:40px"><h2>Error generating report</h2><p>' + escHtml(err.message || String(err)) + '</p></body></html>');
                w.document.close();
            });
        }
    };

    // Keyboard shortcut: Ctrl+K or Cmd+K to toggle chat
    document.addEventListener('keydown', function(e) {
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
            e.preventDefault();
            if (isOpen) window.AnnaChat.close();
            else window.AnnaChat.open();
        }
    });

    // Collapse all suggestion groups except the first
    document.addEventListener('DOMContentLoaded', function() {
        var groups = document.querySelectorAll('.chat-suggest-group');
        for (var i = 1; i < groups.length; i++) {
            groups[i].classList.add('collapsed');
        }
    });

    // ---- AnnaPage: full-page chat with multi-conversation + inline reports ----
})();
