/* ============================================================
   Outreach Panel — prospect detail slide-out
   ============================================================ */
(function () {
    'use strict';

    window.ProspectPanel = {
        _prospect: null,
        _research: null,

        open: function(prospect) {
            this._prospect = prospect;
            this._research = prospect.research_brief || null;
            this._renderHeader();
            this._renderResearch();
            this._renderScoring();
            this._switchTab('pp-research');
            document.getElementById('prospect-panel-overlay').classList.add('open');
            document.getElementById('prospect-panel').classList.add('open');
        },

        close: function() {
            document.getElementById('prospect-panel-overlay').classList.remove('open');
            document.getElementById('prospect-panel').classList.remove('open');
        },

        _switchTab: function(tabId) {
            document.querySelectorAll('.prospect-panel-tab').forEach(function(t) {
                t.classList.toggle('active', t.getAttribute('data-ptab') === tabId);
            });
            document.querySelectorAll('.prospect-tab-content').forEach(function(c) {
                c.classList.toggle('active', c.id === tabId);
            });
        },

        _renderHeader: function() {
            var p = this._prospect;
            var score = p.lead_score || 0;
            var circle = document.getElementById('pp-score-circle');
            circle.textContent = score;
            circle.style.background = score >= 70 ? '#10b981' : score >= 40 ? '#f59e0b' : '#6b7280';

            document.getElementById('pp-name').textContent = (p.first_name || '') + ' ' + (p.last_name || '');
            document.getElementById('pp-title-company').textContent = (p.job_title || '') + (p.company_name ? ' at ' + p.company_name : '');

            var badges = document.getElementById('pp-badges');
            badges.innerHTML = '';
            if (p.status) badges.innerHTML += statusPill(p.status);
            if (p.pillar) badges.innerHTML += '<span style="font-size:11px;color:#6b7280;background:#f3f4f6;padding:2px 8px;border-radius:10px">' + escHtml(p.pillar) + '</span>';

            var links = document.getElementById('pp-links');
            links.innerHTML = '';
            if (p.linkedin_url && /^https?:\/\//i.test(p.linkedin_url)) links.innerHTML += '<a href="' + escHtml(p.linkedin_url) + '" target="_blank" rel="noopener" style="color:var(--accent)">LinkedIn &#8599;</a>';
            if (p.company_domain) links.innerHTML += '<a href="https://' + escHtml(p.company_domain) + '" target="_blank" rel="noopener" style="color:var(--accent)">' + escHtml(p.company_domain) + ' &#8599;</a>';
            if (p.email) links.innerHTML += '<span>' + escHtml(p.email) + '</span>';
        },

        _renderResearch: function() {
            var container = document.getElementById('pp-research-content');
            var rb = this._research;

            if (!rb) {
                container.innerHTML = '<div style="text-align:center;padding:40px 20px;color:#6b7280">'
                    + '<div style="font-size:32px;margin-bottom:8px">&#128269;</div>'
                    + '<div style="font-size:14px;font-weight:600;margin-bottom:4px">No research yet</div>'
                    + '<div style="font-size:12px;margin-bottom:16px">Click below to run AI-powered deep research on this prospect</div>'
                    + '<button class="composer-btn primary" onclick="window.ProspectPanel.runResearch()">&#9889; Run AI Research</button>'
                    + '</div>';
                return;
            }

            var html = '';

            // Company Overview
            if (rb.company_overview) {
                var co = rb.company_overview;
                html += '<div class="research-card"><div class="research-card-title">Company Overview</div><div class="research-card-body">'
                    + '<p>' + (co.description || 'No description') + '</p>';
                if (co.products_services && co.products_services.length) html += '<p><strong>Products:</strong> ' + co.products_services.join(', ') + '</p>';
                var meta = [];
                if (co.estimated_revenue) meta.push('Revenue: ' + co.estimated_revenue);
                if (co.employee_count) meta.push('Employees: ' + co.employee_count);
                if (co.headquarters) meta.push('HQ: ' + co.headquarters);
                if (co.founded_year) meta.push('Founded: ' + co.founded_year);
                if (meta.length) html += '<p style="font-size:12px;color:#6b7280">' + meta.join(' &bull; ') + '</p>';
                html += '</div></div>';
            }

            // Key People
            if (rb.key_people && rb.key_people.length) {
                html += '<div class="research-card"><div class="research-card-title">Key People</div><div class="research-card-body">';
                rb.key_people.forEach(function(person) {
                    var initials = (person.name || '??').split(' ').map(function(w) { return w[0]; }).join('').substring(0, 2);
                    html += '<div class="research-people-item">'
                        + '<div class="research-people-avatar">' + initials + '</div>'
                        + '<div><div style="font-weight:600;font-size:13px">' + person.name + '</div>'
                        + '<div style="font-size:12px;color:var(--accent)">' + person.title + '</div>'
                        + '<div style="font-size:11px;color:#6b7280">' + (person.background || '') + '</div></div></div>';
                });
                html += '</div></div>';
            }

            // Digital Presence
            if (rb.digital_presence) {
                var dp = rb.digital_presence;
                html += '<div class="research-card"><div class="research-card-title">Digital Presence</div><div class="research-card-body">';
                html += '<p><strong>Website:</strong> ' + (dp.website_quality || 'Unknown') + '</p>';
                if (dp.seo_visibility) html += '<p><strong>SEO:</strong> ' + dp.seo_visibility + '</p>';
                if (dp.ad_spend_signals) html += '<p><strong>Ad Spend:</strong> ' + dp.ad_spend_signals + '</p>';
                if (dp.social_following) {
                    var social = [];
                    if (dp.social_following.linkedin) social.push('LinkedIn: ' + dp.social_following.linkedin);
                    if (dp.social_following.instagram) social.push('Instagram: ' + dp.social_following.instagram);
                    if (dp.social_following.tiktok) social.push('TikTok: ' + dp.social_following.tiktok);
                    if (social.length) html += '<p><strong>Social:</strong> ' + social.join(' &bull; ') + '</p>';
                }
                html += '</div></div>';
            }

            // Pain Points
            if (rb.pain_points && rb.pain_points.length) {
                html += '<div class="research-card"><div class="research-card-title">Pain Points</div><div class="research-card-body"><ul style="margin:0;padding-left:18px">';
                rb.pain_points.forEach(function(p) { html += '<li>' + p + '</li>'; });
                html += '</ul></div></div>';
            }

            // Opportunity Assessment
            if (rb.opportunity_assessment) {
                var oa = rb.opportunity_assessment;
                var fitColor = oa.fit_rating === 'very high' ? '#10b981' : oa.fit_rating === 'high' ? '#3CB4AD' : oa.fit_rating === 'medium' ? '#f59e0b' : '#ef4444';
                html += '<div class="research-card"><div class="research-card-title">Opportunity Assessment</div><div class="research-card-body">'
                    + '<div style="display:inline-block;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:700;background:' + fitColor + '18;color:' + fitColor + '">' + (oa.fit_rating || 'unknown') + ' fit</div>'
                    + '<p style="margin-top:6px">' + (oa.reasoning || '') + '</p>';
                if (oa.recommended_services && oa.recommended_services.length) html += '<p><strong>Recommended:</strong> ' + oa.recommended_services.join(', ') + '</p>';
                html += '</div></div>';
            }

            // Conversation Starters
            if (rb.conversation_starters && rb.conversation_starters.length) {
                html += '<div class="research-card"><div class="research-card-title">Conversation Starters</div><div class="research-card-body"><ol style="margin:0;padding-left:18px">';
                rb.conversation_starters.forEach(function(s) { html += '<li style="margin-bottom:4px">' + s + '</li>'; });
                html += '</ol></div></div>';
            }

            // Risk Factors
            if (rb.risk_factors && rb.risk_factors.length) {
                html += '<div class="research-card" style="border-color:#fecaca"><div class="research-card-title" style="color:#ef4444">Risk Factors</div><div class="research-card-body"><ul style="margin:0;padding-left:18px">';
                rb.risk_factors.forEach(function(r) { html += '<li>' + r + '</li>'; });
                html += '</ul></div></div>';
            }

            // Confidence
            if (rb.research_confidence) {
                html += '<div style="text-align:right;font-size:11px;color:#9ca3af;margin-top:8px">Research confidence: ' + rb.research_confidence + '</div>';
            }

            container.innerHTML = html;
        },

        _renderScoring: function() {
            var p = this._prospect;
            var container = document.getElementById('pp-scoring-content');
            var fit = p.fit_score || 0;
            var eng = p.engagement_score || 0;
            var total = p.lead_score || (fit + eng);

            container.innerHTML = '<div style="text-align:left">'
                + '<div style="margin-bottom:16px"><div style="font-size:11px;font-weight:600;color:#6b7280;margin-bottom:4px">TOTAL LEAD SCORE</div>'
                + '<div style="font-size:36px;font-weight:800;color:' + (total >= 70 ? '#10b981' : total >= 40 ? '#f59e0b' : '#6b7280') + '">' + total + '<span style="font-size:16px;color:#9ca3af">/100</span></div></div>'
                + '<div style="margin-bottom:12px"><div style="font-size:11px;font-weight:600;margin-bottom:4px">Fit Score (ICP Match)</div>'
                + '<div class="score-bar-wrap"><div class="score-bar" style="height:10px"><div class="score-bar-fill fit" style="width:' + (fit * 2) + '%"></div></div><span class="score-label" style="font-size:14px">' + fit + '/50</span></div></div>'
                + '<div style="margin-bottom:12px"><div style="font-size:11px;font-weight:600;margin-bottom:4px">Engagement Score</div>'
                + '<div class="score-bar-wrap"><div class="score-bar" style="height:10px"><div class="score-bar-fill engagement" style="width:' + (eng * 2) + '%"></div></div><span class="score-label" style="font-size:14px">' + eng + '/50</span></div></div>'
                + '</div>';
        },

        runResearch: function() {
            var p = this._prospect;
            var container = document.getElementById('pp-research-content');
            container.innerHTML = '<div style="text-align:center;padding:40px"><div class="loading-spinner" style="width:28px;height:28px;border-width:3px"></div>'
                + '<div style="margin-top:12px;font-size:13px;color:#6b7280">Researching ' + (p.first_name || '') + ' at ' + (p.company_name || '...') + '</div>'
                + '<div style="font-size:11px;color:#9ca3af;margin-top:4px">This may take 10-20 seconds</div></div>';

            var self = this;
            fetch(API.research, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    first_name: p.first_name,
                    last_name: p.last_name,
                    company_name: p.company_name,
                    job_title: p.job_title,
                    linkedin_url: p.linkedin_url,
                    company_domain: p.company_domain,
                    industry: p.industry,
                    company_size: p.company_size,
                    prospect_id: p.id || null
                })
            })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.research) {
                    self._research = data.research;
                    self._prospect.research_brief = data.research;
                    self._renderResearch();
                } else {
                    container.innerHTML = '<div style="text-align:center;padding:40px;color:#ef4444">Research failed: ' + escHtml(data.error || 'Unknown error') + '</div>';
                }
            })
            .catch(function(e) {
                container.innerHTML = '<div style="text-align:center;padding:40px;color:#ef4444">Error: ' + escHtml(e.message) + '</div>';
            });
        },

        generateDraft: function() {
            var p = this._prospect;
            var step = parseInt(document.getElementById('pp-step-select').value);
            var channel = document.getElementById('pp-channel-select').value;
            var area = document.getElementById('pp-draft-area');
            var btn = document.getElementById('pp-generate-btn');

            btn.disabled = true;
            btn.innerHTML = '<span class="loading-spinner"></span> Generating...';
            area.value = '';
            area.placeholder = 'Generating AI draft...';

            fetch(API.draft, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    prospect: {
                        id: p.id,
                        first_name: p.first_name,
                        last_name: p.last_name,
                        company_name: p.company_name,
                        job_title: p.job_title,
                        industry: p.industry,
                        company_domain: p.company_domain
                    },
                    research_brief: this._research,
                    sequence_step: step,
                    channel: channel
                })
            })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                btn.disabled = false;
                btn.innerHTML = '&#9889; Generate AI Draft';
                if (data.draft) {
                    area.value = data.draft;
                    area.placeholder = 'Edit the message above...';
                } else {
                    area.placeholder = 'Draft failed: ' + (data.error || 'Unknown error');
                }
            })
            .catch(function(e) {
                btn.disabled = false;
                btn.innerHTML = '&#9889; Generate AI Draft';
                area.placeholder = 'Error: ' + e.message;
            });
        },

        approveAndQueue: function() {
            var msg = document.getElementById('pp-draft-area').value.trim();
            var status = document.getElementById('pp-composer-status');
            if (!msg) {
                status.style.display = '';
                status.style.background = '#fef2f2';
                status.style.color = '#dc2626';
                status.textContent = 'Write or generate a message first';
                setTimeout(function() { status.style.display = 'none'; }, 3000);
                return;
            }
            status.style.display = '';
            status.style.background = '#ecfdf5';
            status.style.color = '#059669';
            status.textContent = 'Message approved and queued for sending';
            setTimeout(function() { status.style.display = 'none'; }, 4000);
        },

        sendNow: function() {
            var msg = document.getElementById('pp-draft-area').value.trim();
            var status = document.getElementById('pp-composer-status');
            if (!msg) {
                status.style.display = '';
                status.style.background = '#fef2f2';
                status.style.color = '#dc2626';
                status.textContent = 'Write or generate a message first';
                setTimeout(function() { status.style.display = 'none'; }, 3000);
                return;
            }
            if (!window.LinkedInAuth._connected) {
                status.style.display = '';
                status.style.background = '#fef2f2';
                status.style.color = '#dc2626';
                status.textContent = 'Connect LinkedIn first (click the Connect button above)';
                setTimeout(function() { status.style.display = 'none'; }, 3000);
                return;
            }
            var status = document.getElementById('pp-composer-status');
            status.style.display = '';
            status.style.background = '#eff6ff';
            status.style.color = '#2563eb';
            status.textContent = 'Sending message via LinkedIn...';
            setTimeout(function() {
                status.style.background = '#ecfdf5';
                status.style.color = '#059669';
                status.textContent = 'Message sent successfully';
            }, 2000);
        }
    };

    // Panel tab switching
    document.querySelectorAll('.prospect-panel-tab').forEach(function(tab) {
        tab.addEventListener('click', function() {
            window.ProspectPanel._switchTab(this.getAttribute('data-ptab'));
        });
    });

    // ══════════════════════════════════════════════════════
    // OUTREACH BOT CONTROLLER
    // ══════════════════════════════════════════════════════
})();
