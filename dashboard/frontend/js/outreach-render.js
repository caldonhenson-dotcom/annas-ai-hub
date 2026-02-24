/* ============================================================
   Outreach Render — 9 sub-tab render functions
   ============================================================ */
(function () {
    'use strict';

    function renderOverview() {
        var f = OD.funnel;
        var el = function(id, v) { var e = document.getElementById(id); if (e) e.textContent = v; };
        el('ov-prospects', f.total_prospects.toLocaleString());
        el('ov-researched', f.researched.toLocaleString());
        el('ov-sent', OD.pillars.reduce(function(s,p){ return s + p.messages_sent; }, 0).toLocaleString());
        var totalSent = OD.pillars.reduce(function(s,p){ return s + p.messages_sent; }, 0);
        var totalRecv = OD.pillars.reduce(function(s,p){ return s + p.messages_received; }, 0);
        el('ov-reply-rate', pct(totalSent > 0 ? totalRecv / totalSent : 0));
        el('ov-conversion', pct(f.total_prospects > 0 ? f.interested / f.total_prospects : 0));
        var avgScore = OD.pillars.reduce(function(s,p){ return s + p.avg_lead_score; }, 0) / OD.pillars.length;
        el('ov-avg-score', avgScore.toFixed(0) + '/100');
        el('ov-ai-calls', OD.ai_usage.total_calls.toLocaleString());
        el('ov-pending', OD.approvals.length);
        el('ov-enrollments', OD.enrollments.filter(function(e){ return e.status === 'active'; }).length);
    }

    // ── 2. Funnel ────────────────────────────────────────
    function renderFunnel() {
        var f = OD.funnel;
        var stages = [
            { label:'Prospects', value:f.total_prospects },
            { label:'Researched', value:f.researched },
            { label:'Enrolled', value:f.enrolled },
            { label:'Contacted', value:f.contacted },
            { label:'Replied', value:f.replied },
            { label:'Interested', value:f.interested },
            { label:'Converted', value:f.converted }
        ];
        var bar = document.getElementById('funnel-bar');
        if (!bar) return;
        var html = '';
        for (var i = 0; i < stages.length; i++) {
            var rate = i > 0 ? pct(stages[i-1].value > 0 ? stages[i].value / stages[i-1].value : 0) : '';
            if (i > 0) html += '<div class="funnel-arrow">&#9654;</div>';
            html += '<div class="funnel-stage">'
                + '<div class="funnel-stage-label">' + stages[i].label + '</div>'
                + '<div class="funnel-stage-value">' + stages[i].value.toLocaleString() + '</div>'
                + (rate ? '<div class="funnel-stage-rate">' + rate + '</div>' : '')
                + '</div>';
        }
        bar.innerHTML = html;

        // Pillar breakdown table
        var tbody = document.getElementById('funnel-pillar-tbody');
        if (!tbody) return;
        html = '';
        OD.pillars.forEach(function(p) {
            html += '<tr><td style="font-weight:600">' + p.name + '</td>'
                + '<td>' + p.prospects + '</td><td>' + p.researched + '</td>'
                + '<td>' + p.enrolled + '</td><td>' + p.contacted + '</td>'
                + '<td>' + p.replied + '</td><td>' + p.interested + '</td>'
                + '<td>' + p.converted + '</td></tr>';
        });
        tbody.innerHTML = html;
    }

    // ── 3. Pillar Performance ────────────────────────────
    function renderPillars() {
        var grid = document.getElementById('pillar-grid');
        if (!grid) return;
        var html = '';
        OD.pillars.forEach(function(p) {
            html += '<div class="pillar-card">'
                + '<div class="pillar-card-header">' + p.name + '</div>'
                + '<div class="pillar-metrics">'
                + '<div><div class="pillar-metric-label">Prospects</div><div class="pillar-metric-value">' + p.prospects + '</div></div>'
                + '<div><div class="pillar-metric-label">Msgs Sent</div><div class="pillar-metric-value">' + p.messages_sent + '</div></div>'
                + '<div><div class="pillar-metric-label">Reply Rate</div><div class="pillar-metric-value">' + pct(p.reply_rate) + '</div></div>'
                + '<div><div class="pillar-metric-label">Conversion</div><div class="pillar-metric-value">' + pct(p.conversion_rate) + '</div></div>'
                + '<div><div class="pillar-metric-label">Avg Score</div><div class="pillar-metric-value">' + p.avg_lead_score + '/100</div></div>'
                + '<div><div class="pillar-metric-label">Interested</div><div class="pillar-metric-value">' + p.interested + '</div></div>'
                + '</div></div>';
        });
        grid.innerHTML = html;
    }

    // ── 4. Approval Queue ────────────────────────────────
    function renderApprovals() {
        var tbody = document.getElementById('approval-tbody');
        if (!tbody) return;
        var html = '';
        OD.approvals.forEach(function(a) {
            html += '<tr>'
                + '<td style="font-weight:600">' + a.prospect + '</td>'
                + '<td>' + a.company + '</td>'
                + '<td style="font-size:11px">' + a.pillar + '</td>'
                + '<td>' + a.channel + '</td>'
                + '<td><div class="message-preview-box">' + a.preview + '</div></td>'
                + '<td style="font-size:11px;color:#6b7280">' + a.model + '</td>'
                + '<td style="font-size:11px;color:#6b7280">' + a.submitted + '</td>'
                + '<td><div class="approval-actions">'
                + '<button class="approval-btn approve" onclick="OutreachActions.approve(' + a.id + ',this)" title="Approve">&#10003;</button>'
                + '<button class="approval-btn reject" onclick="OutreachActions.reject(' + a.id + ',this)" title="Reject">&#10007;</button>'
                + '<button class="approval-btn edit" onclick="showToast(\'Open prospect panel to edit\',\'info\')" title="Edit">&#9998;</button>'
                + '</div></td></tr>';
        });
        tbody.innerHTML = html;
    }

    // ── 5. Lead Leaderboard ──────────────────────────────
    function renderLeaderboard() {
        var tbody = document.getElementById('leaderboard-tbody');
        if (!tbody) return;
        var html = '';
        OD.leaderboard.forEach(function(l) {
            html += '<tr>'
                + '<td style="font-weight:600">' + l.name + '</td>'
                + '<td>' + l.company + '</td>'
                + '<td style="font-size:11px">' + l.pillar + '</td>'
                + '<td style="font-weight:700;font-size:15px">' + l.lead_score + '</td>'
                + '<td><div class="score-bar-wrap"><div class="score-bar"><div class="score-bar-fill fit" style="width:' + (l.fit_score * 2) + '%"></div></div><span class="score-label">' + l.fit_score + '</span></div></td>'
                + '<td><div class="score-bar-wrap"><div class="score-bar"><div class="score-bar-fill engagement" style="width:' + (l.engagement_score * 2) + '%"></div></div><span class="score-label">' + l.engagement_score + '</span></div></td>'
                + '<td>' + statusPill(l.status) + '</td>'
                + '<td style="font-size:11px;color:#6b7280">' + l.last_contact + '</td></tr>';
        });
        tbody.innerHTML = html;
    }

    // ── 6. Active Enrollments ────────────────────────────
    function renderEnrollments() {
        var tbody = document.getElementById('enrollments-tbody');
        if (!tbody) return;
        var html = '';
        OD.enrollments.forEach(function(e) {
            var pctDone = Math.round((e.current_step / e.total_steps) * 100);
            html += '<tr>'
                + '<td style="font-weight:600">' + e.prospect + '</td>'
                + '<td style="font-size:11px">' + e.sequence + '</td>'
                + '<td>' + e.current_step + '/' + e.total_steps + '</td>'
                + '<td style="min-width:100px"><div class="progress-mini"><div class="progress-mini-fill" style="width:' + pctDone + '%"></div></div><div style="font-size:10px;color:#6b7280;margin-top:2px">' + pctDone + '%</div></td>'
                + '<td>' + statusPill(e.status) + '</td>'
                + '<td style="font-size:11px;color:#6b7280">' + e.next_step + '</td>'
                + '<td style="font-size:11px;color:#6b7280">' + e.started + '</td></tr>';
        });
        tbody.innerHTML = html;
    }

    // ── 7. LinkedIn Inbox ────────────────────────────────
    function renderInbox() {
        var list = document.getElementById('inbox-list');
        if (!list) return;
        var html = '';
        OD.inbox.forEach(function(c) {
            html += '<div class="conversation-item' + (c.unread ? ' unread' : '') + '">'
                + '<div class="conversation-avatar">' + c.initials + '</div>'
                + '<div class="conversation-body">'
                + '<div class="conversation-name">' + c.name + ' <span style="font-weight:400;color:#6b7280;font-size:11px">' + c.company + '</span></div>'
                + '<div class="conversation-preview">' + c.preview + '</div>'
                + '</div>'
                + '<div class="conversation-meta">'
                + '<div class="conversation-time">' + c.time + '</div>'
                + (c.unread ? '<div class="conversation-unread-dot"></div>' : '')
                + '</div></div>';
        });
        list.innerHTML = html;
    }

    // ── 8. AI Usage ──────────────────────────────────────
    function renderAIUsage() {
        var ai = OD.ai_usage;
        var el = function(id, v) { var e = document.getElementById(id); if (e) e.textContent = v; };
        el('ai-total-calls', ai.total_calls.toLocaleString());
        el('ai-total-cost', '\u00a3' + ai.est_cost.toFixed(2));
        el('ai-avg-latency', ai.avg_latency_ms + 'ms');
        el('ai-success-rate', pct(ai.success_rate));

        var tbody = document.getElementById('ai-usage-tbody');
        if (!tbody) return;
        var html = '';
        ai.breakdown.forEach(function(r) {
            html += '<tr>'
                + '<td style="font-weight:600">' + r.provider + '</td>'
                + '<td>' + r.task + '</td>'
                + '<td>' + r.calls.toLocaleString() + '</td>'
                + '<td>' + (r.tokens / 1000).toFixed(0) + 'K</td>'
                + '<td>' + r.avg_latency + 'ms</td>'
                + '<td>' + r.p95_latency + 'ms</td>'
                + '<td>' + pct(r.success_rate) + '</td></tr>';
        });
        tbody.innerHTML = html;
    }

    // ── 9. Correspondence ────────────────────────────────
    function renderCorrespondence() {
        var tbody = document.getElementById('correspondence-tbody');
        if (!tbody) return;
        var html = '';
        OD.correspondence.forEach(function(c) {
            html += '<tr>'
                + '<td style="font-weight:600">' + c.from + '</td>'
                + '<td>' + c.company + '</td>'
                + '<td>' + c.channel + '</td>'
                + '<td><span class="intent-badge ' + c.intent + '">' + c.intent.replace('-', ' ') + '</span></td>'
                + '<td style="font-weight:600">' + pct(c.confidence) + '</td>'
                + '<td>' + statusPill(c.sentiment) + '</td>'
                + '<td><div class="message-preview-box">' + c.preview + '</div></td>'
                + '<td style="font-size:11px;color:#6b7280">' + c.time + '</td></tr>';
        });
        tbody.innerHTML = html;
    }

    // ── Render all outreach sub-tabs ─────────────────────
    function renderAllOutreach() {
        renderOverview();
        renderFunnel();
        renderPillars();
        renderApprovals();
        renderLeaderboard();
        renderEnrollments();
        renderInbox();
        renderAIUsage();
        renderCorrespondence();
    }

    // ── Live data loader (Supabase → OD, fallback to demo) ──
    function loadLiveOutreachData() {
        fetch(API.outreachData)
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (!data.live) return; // No live data, keep demo
                // Merge live data into OD
                if (data.funnel) OD.funnel = data.funnel;
                if (data.leaderboard && data.leaderboard.length) OD.leaderboard = data.leaderboard;
                if (data.approvals && data.approvals.length) OD.approvals = data.approvals;
                if (data.ai_usage) OD.ai_usage = data.ai_usage;
                // Re-render with live data
                renderAllOutreach();
                showToast('Live data loaded from Supabase', 'success');
            })
            .catch(function() { /* keep demo data */ });
    }

    // ── Init ─────────────────────────────────────────────
    document.addEventListener('DOMContentLoaded', function() {
        renderAllOutreach();
        loadLiveOutreachData();
    });

    // Also run immediately if DOM already loaded
    if (document.readyState !== 'loading') {
        renderAllOutreach();
        loadLiveOutreachData();
    }

    // ══════════════════════════════════════════════════════
    // LINKEDIN AUTH CONTROLLER (Extension-powered single-click)
    // ══════════════════════════════════════════════════════
    // Chrome extension ID — set after loading unpacked extension
    // The extension's externally_connectable matches our origin
    var LI_EXTENSION_ID = null;

})();
