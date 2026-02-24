/* ============================================================
   Outreach Bot — AI research, drafting, intent classification
   ============================================================ */
(function () {
    'use strict';

    window.OutreachBot = {
        _state: 'idle',
        _heartbeatInterval: null,

        start: function() {
            this._state = 'running';
            this._updateUI();
            this._startHeartbeat();
        },

        pause: function() {
            this._state = 'paused';
            this._updateUI();
            this._stopHeartbeat();
        },

        stop: function() {
            this._state = 'idle';
            this._updateUI();
            this._stopHeartbeat();
        },

        _updateUI: function() {
            var dot = document.getElementById('bot-dot');
            var label = document.getElementById('bot-status-label');
            var startBtn = document.getElementById('bot-start');
            var pauseBtn = document.getElementById('bot-pause');
            var stopBtn = document.getElementById('bot-stop');

            dot.className = 'bot-status-dot ' + this._state;
            label.textContent = this._state.charAt(0).toUpperCase() + this._state.slice(1);

            startBtn.disabled = this._state === 'running';
            pauseBtn.disabled = this._state !== 'running';
            stopBtn.disabled = this._state === 'idle';
        },

        _startHeartbeat: function() {
            var hb = document.getElementById('bot-heartbeat');
            this._heartbeatInterval = setInterval(function() {
                fetch(API.session, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'heartbeat' })
                })
                .then(function() {
                    if (hb) hb.textContent = new Date().toLocaleTimeString('en-GB', { hour:'2-digit', minute:'2-digit' });
                })
                .catch(function() {
                    if (hb) hb.textContent = 'err';
                });
            }, 60000);
            // Immediate first heartbeat
            if (hb) hb.textContent = new Date().toLocaleTimeString('en-GB', { hour:'2-digit', minute:'2-digit' });
            fetch(API.session, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'heartbeat' })
            }).catch(function(){});
        },

        _stopHeartbeat: function() {
            if (this._heartbeatInterval) {
                clearInterval(this._heartbeatInterval);
                this._heartbeatInterval = null;
            }
            var hb = document.getElementById('bot-heartbeat');
            if (hb) hb.textContent = '--';
        }
    };

    // ══════════════════════════════════════════════════════
    // MAKE PROSPECT NAMES CLICKABLE
    // ══════════════════════════════════════════════════════
    window.openProspect = function(prospectData) {
        window.ProspectPanel.open(prospectData);
    };

    // Override renderers to make names clickable
    var _origApprovals = renderApprovals;
    renderApprovals = function() {
        var tbody = document.getElementById('approval-tbody');
        if (!tbody) return;
        var html = '';
        OD.approvals.forEach(function(a) {
            var pData = JSON.stringify({
                first_name: a.prospect.split(' ')[0],
                last_name: a.prospect.split(' ').slice(1).join(' '),
                company_name: a.company,
                pillar: a.pillar,
                lead_score: 0, fit_score: 0, engagement_score: 0,
                status: 'pending'
            }).replace(/'/g, "\\'");
            html += '<tr>'
                + '<td><a href="#" onclick="event.preventDefault();window.openProspect(' + pData.replace(/"/g, '&quot;') + ')" style="font-weight:600;color:var(--accent);text-decoration:none">' + a.prospect + '</a></td>'
                + '<td>' + a.company + '</td>'
                + '<td style="font-size:11px">' + a.pillar + '</td>'
                + '<td>' + a.channel + '</td>'
                + '<td><div class="message-preview-box">' + a.preview + '</div></td>'
                + '<td style="font-size:11px;color:#6b7280">' + a.model + '</td>'
                + '<td style="font-size:11px;color:#6b7280">' + a.submitted + '</td>'
                + '<td><div class="approval-actions">'
                + '<button class="approval-btn approve" onclick="OutreachActions.approve(' + a.id + ',this)" title="Approve">&#10003;</button>'
                + '<button class="approval-btn reject" onclick="OutreachActions.reject(' + a.id + ',this)" title="Reject">&#10007;</button>'
                + '<button class="approval-btn edit" onclick="event.preventDefault();var p=' + pData.replace(/"/g, '&quot;') + ';window.ProspectPanel.open(p);window.ProspectPanel._switchTab(\'pp-composer\');document.getElementById(\'pp-draft-area\').value=\'' + a.preview.replace(/'/g, "\\'").substring(0, 120) + '...\'" title="Edit">&#9998;</button>'
                + '</div></td></tr>';
        });
        tbody.innerHTML = html;
    };

    var _origLeaderboard = renderLeaderboard;
    renderLeaderboard = function() {
        var tbody = document.getElementById('leaderboard-tbody');
        if (!tbody) return;
        var html = '';
        OD.leaderboard.forEach(function(l) {
            var pData = JSON.stringify({
                first_name: l.name.split(' ')[0],
                last_name: l.name.split(' ').slice(1).join(' '),
                company_name: l.company,
                pillar: l.pillar,
                lead_score: l.lead_score,
                fit_score: l.fit_score,
                engagement_score: l.engagement_score,
                status: l.status
            }).replace(/'/g, "\\'");
            html += '<tr>'
                + '<td><a href="#" onclick="event.preventDefault();window.openProspect(' + pData.replace(/"/g, '&quot;') + ')" style="font-weight:600;color:var(--accent);text-decoration:none">' + l.name + '</a></td>'
                + '<td>' + l.company + '</td>'
                + '<td style="font-size:11px">' + l.pillar + '</td>'
                + '<td style="font-weight:700;font-size:15px">' + l.lead_score + '</td>'
                + '<td><div class="score-bar-wrap"><div class="score-bar"><div class="score-bar-fill fit" style="width:' + (l.fit_score * 2) + '%"></div></div><span class="score-label">' + l.fit_score + '</span></div></td>'
                + '<td><div class="score-bar-wrap"><div class="score-bar"><div class="score-bar-fill engagement" style="width:' + (l.engagement_score * 2) + '%"></div></div><span class="score-label">' + l.engagement_score + '</span></div></td>'
                + '<td>' + statusPill(l.status) + '</td>'
                + '<td style="font-size:11px;color:#6b7280">' + l.last_contact + '</td></tr>';
        });
        tbody.innerHTML = html;
    };

    // Re-render with clickable names
    renderApprovals();
    renderLeaderboard();

        })();
})();
