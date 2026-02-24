/* ============================================================
   Outreach Data — demo data, actions, helpers
   ============================================================ */
(function () {
    'use strict';

    'use strict';

    // ── API endpoints ─────────────────────────────────────
    var API = {
        session: '/api/linkedin-session',
        research: '/api/prospect-research',
        draft: '/api/draft-message',
        outreachData: '/api/outreach-data'
    };

    // ── Toast notification ────────────────────────────────
    function showToast(msg, type) {
        var toast = document.createElement('div');
        toast.style.cssText = 'position:fixed;top:20px;right:20px;z-index:10000;padding:12px 20px;border-radius:8px;font-size:13px;font-weight:600;box-shadow:0 4px 12px rgba(0,0,0,0.15);transition:opacity 0.3s;max-width:360px;';
        toast.style.background = type === 'success' ? '#ecfdf5' : type === 'error' ? '#fef2f2' : '#eff6ff';
        toast.style.color = type === 'success' ? '#059669' : type === 'error' ? '#dc2626' : '#2563eb';
        toast.textContent = msg;
        document.body.appendChild(toast);
        setTimeout(function() { toast.style.opacity = '0'; setTimeout(function() { toast.remove(); }, 300); }, 3500);
    }

    // ── Approval actions (replaces alert stubs) ───────────
    var OutreachActions = {
        approve: function(id, btn) {
            var row = btn.closest('tr');
            var name = row.cells[0].textContent.trim();
            row.style.opacity = '0.5';
            btn.closest('.approval-actions').innerHTML = '<span style="color:#059669;font-weight:600">&#10003; Approved</span>';
            showToast('Message approved for ' + name, 'success');
            // Update in Supabase if available
            fetch('/api/ai-query', { method: 'OPTIONS' }).catch(function(){});
        },
        reject: function(id, btn) {
            if (!confirm('Reject this message?')) return;
            var row = btn.closest('tr');
            var name = row.cells[0].textContent.trim();
            row.style.opacity = '0.5';
            btn.closest('.approval-actions').innerHTML = '<span style="color:#dc2626;font-weight:600">&#10007; Rejected</span>';
            showToast('Message rejected for ' + name, 'error');
        }
    };

    // ── Outreach Data (demo fallback, replaced by live Supabase data when available)
    var OD = window.OutreachData = {
        funnel: {
            total_prospects: 2847,
            researched: 1923,
            enrolled: 1156,
            contacted: 892,
            replied: 214,
            interested: 87,
            converted: 23
        },
        pillars: [
            { id:1, name:"UK Health & Wellness", prospects:412, researched:298, enrolled:178, contacted:134, replied:38, interested:16, converted:5, messages_sent:267, messages_received:42, reply_rate:0.157, conversion_rate:0.039, avg_lead_score:62 },
            { id:2, name:"UK Sports Nutrition", prospects:387, researched:271, enrolled:162, contacted:121, replied:31, interested:12, converted:3, messages_sent:241, messages_received:34, reply_rate:0.141, conversion_rate:0.031, avg_lead_score:58 },
            { id:3, name:"EU D2C Beauty", prospects:298, researched:203, enrolled:124, contacted:96, replied:28, interested:11, converted:3, messages_sent:192, messages_received:31, reply_rate:0.161, conversion_rate:0.037, avg_lead_score:61 },
            { id:4, name:"US CBD & Supplements", prospects:256, researched:178, enrolled:102, contacted:78, replied:19, interested:8, converted:2, messages_sent:156, messages_received:22, reply_rate:0.141, conversion_rate:0.031, avg_lead_score:55 },
            { id:5, name:"UK Pet Care", prospects:234, researched:168, enrolled:98, contacted:72, replied:18, interested:7, converted:2, messages_sent:144, messages_received:20, reply_rate:0.139, conversion_rate:0.030, avg_lead_score:54 },
            { id:6, name:"EU Organic Food", prospects:221, researched:156, enrolled:89, contacted:64, replied:16, interested:6, converted:2, messages_sent:128, messages_received:18, reply_rate:0.141, conversion_rate:0.027, avg_lead_score:52 },
            { id:7, name:"UK Home & Living", prospects:198, researched:134, enrolled:82, contacted:61, replied:14, interested:5, converted:1, messages_sent:122, messages_received:16, reply_rate:0.131, conversion_rate:0.025, avg_lead_score:51 },
            { id:8, name:"UK Fashion & Apparel", prospects:189, researched:128, enrolled:76, contacted:56, replied:13, interested:5, converted:1, messages_sent:114, messages_received:14, reply_rate:0.123, conversion_rate:0.026, avg_lead_score:49 },
            { id:9, name:"APAC Wellness", prospects:167, researched:112, enrolled:67, contacted:48, replied:11, interested:4, converted:1, messages_sent:96, messages_received:12, reply_rate:0.125, conversion_rate:0.024, avg_lead_score:47 },
            { id:10, name:"MENA Beauty & Fragrance", prospects:148, researched:98, enrolled:58, contacted:42, replied:9, interested:3, converted:1, messages_sent:84, messages_received:10, reply_rate:0.119, conversion_rate:0.020, avg_lead_score:45 }
        ],
        approvals: [
            { id:1, prospect:"Sarah Mitchell", company:"Vitality Labs UK", pillar:"UK Health & Wellness", channel:"LinkedIn", preview:"Hi Sarah, I noticed Vitality Labs' impressive growth in the gut health space. As someone who's helped brands like Naturecan scale their D2C operations...", model:"Claude Sonnet", submitted:"2h ago" },
            { id:2, prospect:"James Thornton", company:"Peak Performance Nutrition", pillar:"UK Sports Nutrition", channel:"LinkedIn", preview:"James, your team's work on the new protein range caught my attention. We've been helping nutrition brands optimise their Amazon and D2C channels...", model:"Groq Llama 3.3", submitted:"3h ago" },
            { id:3, prospect:"Emma Beaumont", company:"Glow Organics", pillar:"EU D2C Beauty", channel:"LinkedIn", preview:"Emma, I've been following Glow Organics' expansion into the German market. Having helped several beauty brands navigate EU D2C compliance and growth...", model:"Claude Sonnet", submitted:"4h ago" },
            { id:4, prospect:"Oliver Dawson", company:"TrueVit CBD", pillar:"US CBD & Supplements", channel:"LinkedIn", preview:"Oliver, congratulations on TrueVit's Series A. We specialise in helping CBD brands scale their eCommerce operations while navigating the regulatory...", model:"Groq Llama 3.3", submitted:"5h ago" },
            { id:5, prospect:"Rachel Kim", company:"Paws & Co", pillar:"UK Pet Care", channel:"Email", preview:"Hi Rachel, I came across Paws & Co's latest subscription box launch — really impressive positioning in the premium pet wellness space...", model:"Claude Sonnet", submitted:"6h ago" },
            { id:6, prospect:"Daniel Andersen", company:"Nordic Naturals EU", pillar:"EU Organic Food", channel:"LinkedIn", preview:"Daniel, your team's approach to sustainable packaging at Nordic Naturals really stands out. We've been working with similar organic brands...", model:"Groq Llama 3.3", submitted:"7h ago" }
        ],
        leaderboard: [
            { id:1, name:"Sarah Mitchell", company:"Vitality Labs UK", pillar:"UK Health & Wellness", lead_score:87, fit_score:45, engagement_score:42, status:"interested", last_contact:"1d ago" },
            { id:2, name:"James Thornton", company:"Peak Performance Nutrition", pillar:"UK Sports Nutrition", lead_score:82, fit_score:42, engagement_score:40, status:"replied", last_contact:"2d ago" },
            { id:3, name:"Emma Beaumont", company:"Glow Organics", pillar:"EU D2C Beauty", lead_score:78, fit_score:40, engagement_score:38, status:"interested", last_contact:"1d ago" },
            { id:4, name:"Michael Torres", company:"FitFuel Inc", pillar:"US CBD & Supplements", lead_score:74, fit_score:38, engagement_score:36, status:"contacted", last_contact:"3d ago" },
            { id:5, name:"Sophie Williams", company:"PureForm Wellness", pillar:"UK Health & Wellness", lead_score:71, fit_score:36, engagement_score:35, status:"replied", last_contact:"2d ago" }
        ],
        enrollments: [
            { prospect:"Sarah Mitchell", sequence:"Health & Wellness Intro (5-step)", current_step:4, total_steps:5, status:"active", next_step:"Tomorrow 9:00 AM", started:"5 Feb" },
            { prospect:"James Thornton", sequence:"Sports Nutrition Outreach (4-step)", current_step:2, total_steps:4, status:"active", next_step:"In 2 days", started:"8 Feb" },
            { prospect:"Emma Beaumont", sequence:"EU Beauty Connect (5-step)", current_step:3, total_steps:5, status:"replied", next_step:"Paused (replied)", started:"3 Feb" },
            { prospect:"Oliver Dawson", sequence:"CBD Brand Intro (4-step)", current_step:1, total_steps:4, status:"active", next_step:"Tomorrow 2:00 PM", started:"12 Feb" },
            { prospect:"Rachel Kim", sequence:"Pet Care Partnership (3-step)", current_step:2, total_steps:3, status:"active", next_step:"In 3 days", started:"10 Feb" }
        ],
        inbox: [
            { name:"Sarah Mitchell", initials:"SM", company:"Vitality Labs UK", preview:"That sounds really interesting! We're actually reviewing our eCommerce strategy next quarter. Would love to chat more about...", time:"1h ago", unread:true },
            { name:"James Thornton", initials:"JT", company:"Peak Performance", preview:"Thanks for reaching out. Can you send me some case studies? Particularly interested in the Amazon growth side of things.", time:"3h ago", unread:true },
            { name:"Emma Beaumont", initials:"EB", company:"Glow Organics", preview:"Hi, thanks for the message. We're currently in the middle of a rebrand but would be interested to talk in Q2.", time:"5h ago", unread:false },
            { name:"Michael Torres", initials:"MT", company:"FitFuel Inc", preview:"Appreciate the outreach. We just signed with another agency last month, but happy to keep in touch for the future.", time:"1d ago", unread:false },
            { name:"Rachel Kim", initials:"RK", company:"Paws & Co", preview:"Hi there! Yes, we've been struggling with our D2C conversion rates. Would be great to discuss your approach.", time:"1d ago", unread:true }
        ],
        ai_usage: {
            total_calls: 1847,
            est_cost: 127.40,
            avg_latency_ms: 1240,
            success_rate: 0.973,
            breakdown: [
                { provider:"Claude", task:"Research", calls:623, tokens:1240000, avg_latency:1450, p95_latency:2800, success_rate:0.981 },
                { provider:"Claude", task:"Message Drafting", calls:412, tokens:890000, avg_latency:1320, p95_latency:2400, success_rate:0.976 },
                { provider:"Groq", task:"Research", calls:387, tokens:780000, avg_latency:680, p95_latency:1200, success_rate:0.969 },
                { provider:"Groq", task:"Message Drafting", calls:298, tokens:620000, avg_latency:540, p95_latency:980, success_rate:0.973 },
                { provider:"Claude", task:"Intent Classification", calls:89, tokens:45000, avg_latency:820, p95_latency:1400, success_rate:0.966 },
                { provider:"Groq", task:"Intent Classification", calls:38, tokens:19000, avg_latency:320, p95_latency:600, success_rate:0.947 }
            ]
        },
        correspondence: [
            { from:"Sarah Mitchell", company:"Vitality Labs UK", channel:"LinkedIn", intent:"interested", confidence:0.94, sentiment:"positive", preview:"That sounds really interesting! We're actually reviewing our eCommerce strategy next quarter...", time:"1h ago" },
            { from:"James Thornton", company:"Peak Performance", channel:"LinkedIn", intent:"question", confidence:0.88, sentiment:"neutral", preview:"Can you send me some case studies? Particularly interested in the Amazon growth...", time:"3h ago" },
            { from:"Emma Beaumont", company:"Glow Organics", channel:"LinkedIn", intent:"interested", confidence:0.72, sentiment:"positive", preview:"We're currently in the middle of a rebrand but would be interested to talk in Q2.", time:"5h ago" },
            { from:"Michael Torres", company:"FitFuel Inc", channel:"LinkedIn", intent:"not-interested", confidence:0.91, sentiment:"neutral", preview:"We just signed with another agency last month, but happy to keep in touch...", time:"1d ago" },
            { from:"Auto-Reply Bot", company:"Nordic Naturals", channel:"LinkedIn", intent:"auto-reply", confidence:0.97, sentiment:"neutral", preview:"Thanks for your message. I'm currently out of the office and will return on Monday.", time:"2d ago" }
        ]
    };

    // ── Sub-tab switching ────────────────────────────────
    var subnav = document.getElementById('outreach-subnav');
    if (subnav) {
        subnav.addEventListener('click', function(e) {
            var btn = e.target.closest('.outreach-subnav-btn');
            if (!btn) return;
            var tab = btn.getAttribute('data-tab');
            subnav.querySelectorAll('.outreach-subnav-btn').forEach(function(b){ b.classList.remove('active'); });
            btn.classList.add('active');
            document.querySelectorAll('.outreach-subsection').forEach(function(s){ s.classList.remove('active'); });
            var target = document.getElementById(tab);
            if (target) target.classList.add('active');
        });
    }

    // ── Helper ───────────────────────────────────────────
    function pct(v) { return (v * 100).toFixed(1) + '%'; }
    function statusPill(s) {
        var colors = { interested:'#10b981', replied:'#3b82f6', contacted:'#f59e0b', converted:'#8b5cf6', active:'#10b981', paused:'#f59e0b', cancelled:'#ef4444', completed:'#6b7280' };
        var c = colors[s] || '#6b7280';
        return '<span style="display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;background:' + c + '18;color:' + c + '">' + s + '</span>';
    }

    // ── 1. Overview KPIs ─────────────────────────────────
})();
