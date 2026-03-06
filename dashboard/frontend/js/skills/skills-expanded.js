/* ============================================================
   Skills Expanded — rich detail card, context, blocks, favourites
   ============================================================ */
(function () {
    'use strict';

    var _expandedId = null;
    var _features = {};
    var HISTORY_KEY = 'ecomplete_skill_history';

    // Persona tags by category (derived from user persona audit)
    var PERSONA_MAP = {
        'deal-sourcing': ['BD Team', 'SDRs'],
        'nda-legal': ['Legal', 'Compliance'],
        'email-comms': ['MD', 'Sales Team'],
        'cdd': ['CDD Analysts', 'Investors'],
        'pipeline': ['Deal Team', 'MD'],
        'ops': ['COO', 'Ops Team'],
        'reporting-intel': ['Board', 'Strategy'],
        'board-reporting': ['Board', 'Investors'],
        'market-intel': ['Strategy', 'BD Team'],
        'data-systems': ['Ops Team', 'Data Lead'],
        'ecommerce': ['eCommerce', 'Strategy']
    };

    function esc(s) { var d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

    // ------------------------------------------------------------------
    // Derived metadata helpers (no category file changes needed)
    // ------------------------------------------------------------------
    function getOutputType(skill) {
        var exec = skill.execute || {};
        if (exec.resultType === 'draft') return 'Draft';
        if (exec.type === 'api-call' || exec.type === 'client-only') return 'Action';
        var actions = exec.actions || [];
        for (var i = 0; i < actions.length; i++) {
            if (actions[i].handler === 'exportPdf') return 'Report';
        }
        return 'Analysis';
    }

    function getLastRun(skillId) {
        try {
            var h = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
            for (var i = h.length - 1; i >= 0; i--) {
                if (h[i].skillId === skillId) return h[i];
            }
        } catch (e) { /* empty */ }
        return null;
    }

    function getRunCount(skillId) {
        try {
            var h = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
            var monthAgo = Date.now() - 2592000000;
            return h.filter(function (e) { return e.skillId === skillId && e.timestamp > monthAgo; }).length;
        } catch (e) { return 0; }
    }

    function timeAgo(ts) {
        var d = Date.now() - ts;
        if (d < 60000) return 'just now';
        if (d < 3600000) return Math.floor(d / 60000) + 'm ago';
        if (d < 86400000) return Math.floor(d / 3600000) + 'h ago';
        return Math.floor(d / 86400000) + 'd ago';
    }

    function getMissingConnectors(skill) {
        if (!skill.blocks || !window.Blocks || !window.Connectors) return [];
        var missing = [];
        skill.blocks.forEach(function (b) {
            if (b.role !== 'core') return;
            var blk = window.Blocks ? window.Blocks.get(b.id) : null;
            if (!blk || window.Blocks.isAvailable(b.id)) return;
            (blk.requires || []).forEach(function (cid) {
                if (!window.Connectors.isAvailable(cid) && missing.indexOf(cid) === -1) missing.push(cid);
            });
        });
        return missing;
    }

    // ------------------------------------------------------------------
    // Open / close expanded card
    // ------------------------------------------------------------------
    function open(skillId) {
        if (_expandedId === skillId) { close(); return; }
        close();
        _expandedId = skillId;
        var skill = window.SkillsRegistry.get(skillId);
        if (!skill) return;
        var card = document.querySelector('.skill-card[data-skill-id="' + skillId + '"]');
        if (!card) return;
        card.classList.add('expanded');
        if (!_features[skillId] && skill.features) {
            _features[skillId] = {};
            skill.features.forEach(function (f) { _features[skillId][f.id] = f.default !== false; });
        }
        var body = document.createElement('div');
        body.className = 'skill-expanded-body';
        body.innerHTML = contextHtml(skill) + warningHtml(skill) + blocksHtml(skill)
            + featuresHtml(skill) + inputsPreviewHtml(skill) + actionsHtml(skill);
        card.appendChild(body);
        card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    function close() {
        if (!_expandedId) return;
        var card = document.querySelector('.skill-card.expanded');
        if (card) {
            card.classList.remove('expanded');
            var b = card.querySelector('.skill-expanded-body');
            if (b) b.remove();
        }
        _expandedId = null;
    }

    // ------------------------------------------------------------------
    // Context section (personas, output type, last run, run count)
    // ------------------------------------------------------------------
    function contextHtml(skill) {
        var personas = PERSONA_MAP[skill.category] || PERSONA_MAP[skill.subcategory] || ['All Users'];
        var outType = getOutputType(skill);
        var last = getLastRun(skill.id);
        var runs = getRunCount(skill.id);
        var personaTags = personas.map(function (p) {
            return '<span class="exp-persona-tag">' + esc(p) + '</span>';
        }).join('');
        var lastHtml = last
            ? '<span class="exp-last-run' + (last.success ? '' : ' failed') + '">'
            + (last.success ? '&#10003;' : '&#10007;') + ' ' + timeAgo(last.timestamp) + '</span>'
            : '<span class="exp-last-run muted">Never run</span>';
        var runsHtml = runs > 0 ? ' &middot; <span>' + runs + 'x this month</span>' : '';
        return '<div class="skill-context-section">'
            + '<div class="skill-context-row">'
            + '<span class="skill-context-label">&#128100;</span>' + personaTags
            + '<span class="exp-output-tag tag-' + outType.toLowerCase() + '">' + outType + '</span>'
            + (skill.estimatedTime ? '<span class="exp-est-tag">&#9201; ' + esc(skill.estimatedTime) + '</span>' : '')
            + '</div>'
            + '<div class="skill-context-row">'
            + '<span class="skill-context-label">&#9889; Last:</span>' + lastHtml + runsHtml
            + '</div></div>';
    }

    // ------------------------------------------------------------------
    // Missing connector warnings
    // ------------------------------------------------------------------
    function warningHtml(skill) {
        var missing = getMissingConnectors(skill);
        if (missing.length === 0) return '';
        var names = missing.map(function (cid) {
            var c = window.Connectors ? window.Connectors.get(cid) : null;
            return c ? c.name : cid;
        });
        return '<div class="skill-warning-bar">&#9888; Required: '
            + esc(names.join(', '))
            + ' not connected &mdash; skill may not run</div>';
    }

    // ------------------------------------------------------------------
    // Blocks visualization
    // ------------------------------------------------------------------
    function blocksHtml(skill) {
        var blocks = skill.blocks;
        if (!blocks || blocks.length === 0) return '';
        return '<div class="skill-blocks-section"><div class="skill-blocks-label">Building Blocks</div>'
            + '<div class="skill-blocks-grid">'
            + blocks.map(function (b) {
                var blk = window.Blocks ? window.Blocks.get(b.id) : null;
                var ok = window.Blocks ? window.Blocks.isAvailable(b.id) : false;
                var rc = b.role === 'core' ? 'role-core' : b.role === 'enhance' ? 'role-enhance' : 'role-output';
                return '<div class="skill-block-chip">'
                    + '<span class="connector-dot ' + (ok ? 'dot-green' : 'dot-gray') + '"></span>'
                    + '<span>' + (blk ? blk.icon : '') + '</span>'
                    + '<span>' + esc(b.label || (blk ? blk.name : b.id)) + '</span>'
                    + '<span class="skill-block-role ' + rc + '">' + b.role + '</span></div>';
            }).join('') + '</div></div>';
    }

    // ------------------------------------------------------------------
    // Feature toggles
    // ------------------------------------------------------------------
    function featuresHtml(skill) {
        if (!skill.features || skill.features.length === 0) return '';
        var st = _features[skill.id] || {};
        return '<div class="skill-features-section"><div class="skill-features-label">Features</div>'
            + '<div class="skill-features-grid">'
            + skill.features.map(function (f) {
                return '<label class="skill-feature-toggle">'
                    + '<input type="checkbox"' + (st[f.id] !== false ? ' checked' : '')
                    + ' onchange="window.SkillsExpanded.toggleFeature(\'' + skill.id + '\',\'' + f.id + '\')">'
                    + ' ' + esc(f.label) + '</label>';
            }).join('') + '</div></div>';
    }

    function toggleFeature(sid, fid) {
        if (!_features[sid]) _features[sid] = {};
        _features[sid][fid] = !_features[sid][fid];
    }

    // ------------------------------------------------------------------
    // Input requirements preview
    // ------------------------------------------------------------------
    function inputsPreviewHtml(skill) {
        var inputs = (skill.execute || {}).inputs || [];
        if (inputs.length === 0) {
            return '<div class="skill-inputs-preview"><span class="skill-blocks-label">Inputs</span>'
                + '<span class="exp-no-inputs">No configuration needed &mdash; runs immediately</span></div>';
        }
        return '<div class="skill-inputs-preview"><span class="skill-blocks-label">Required Inputs</span>'
            + '<div class="exp-inputs-grid">'
            + inputs.map(function (inp) {
                var typeBadge = inp.type === 'select' ? 'select' : inp.type === 'textarea' ? 'text area' : inp.type || 'text';
                return '<span class="exp-input-tag' + (inp.required ? ' required' : '') + '">'
                    + esc(inp.label) + (inp.required ? ' *' : '')
                    + '<span class="exp-input-type">' + typeBadge + '</span></span>';
            }).join('') + '</div></div>';
    }

    // ------------------------------------------------------------------
    // Enhanced actions row (skill-specific + standard buttons)
    // ------------------------------------------------------------------
    function actionsHtml(skill) {
        var fav = isFav(skill.id);
        var stars = '';
        for (var i = 1; i <= 5; i++) stars += '<span class="skill-star' + (i <= skill.impact ? ' filled' : '') + '">&#9733;</span>';
        // Skill-specific actions from execute.actions (disabled until result exists)
        var skillActions = (skill.execute.actions || []).map(function (a) {
            var icon = a.handler === 'copyResult' ? '&#128203;' : a.handler === 'exportPdf' ? '&#128196;' : '&#9889;';
            return '<button class="skill-close-btn" disabled title="Run skill first" '
                + 'onclick="event.stopPropagation()">' + icon + ' ' + esc(a.label) + '</button>';
        }).join('');
        return '<div class="skill-expanded-actions">'
            + '<div class="skill-expanded-meta">'
            + stars + (skill.timeSaved ? ' &middot; Saves ~' + skill.timeSaved + 'min' : '')
            + '</div>'
            + skillActions
            + '<button class="skill-fav-btn' + (fav ? ' is-fav' : '') + '" '
            + 'onclick="event.stopPropagation();window.SkillsExpanded.toggleFav(\'' + skill.id + '\')" '
            + 'title="Favourite">&#9733;</button>'
            + '<button class="skill-exec-btn" style="flex:0 0 auto;padding:8px 20px" '
            + 'onclick="event.stopPropagation();window.SkillsUI.openExecModal(\'' + skill.id + '\')"'
            + (skill.status !== 'ready' ? ' disabled' : '') + '>&#9889; Execute</button>'
            + '<button class="skill-close-btn" onclick="event.stopPropagation();'
            + 'window.SkillsExpanded.close()">&#10005; Close</button>'
            + '</div>';
    }

    // ------------------------------------------------------------------
    // Skill favourites (store name+icon for sidebar use on any page)
    // ------------------------------------------------------------------
    function getFavs() {
        var prefs = window.loadPrefs ? window.loadPrefs() : {};
        return Array.isArray(prefs.skillFavs) ? prefs.skillFavs : [];
    }

    function isFav(skillId) {
        return getFavs().some(function (f) { return f.id === skillId; });
    }

    function toggleFav(skillId) {
        var favs = getFavs();
        var idx = -1;
        favs.forEach(function (f, i) { if (f.id === skillId) idx = i; });
        if (idx === -1) {
            var skill = window.SkillsRegistry ? window.SkillsRegistry.get(skillId) : null;
            favs.push({ id: skillId, name: skill ? skill.name : skillId, icon: skill ? (skill.icon || '&#9889;') : '&#9889;' });
        } else {
            favs.splice(idx, 1);
        }
        if (window.savePrefs) window.savePrefs({ skillFavs: favs });
        var expBtn = document.querySelector('.skill-expanded-actions .skill-fav-btn');
        if (expBtn) expBtn.classList.toggle('is-fav', idx === -1);
        var cardBtn = document.querySelector('.skill-card[data-skill-id="' + skillId + '"] > .skill-card-header .skill-fav-btn');
        if (cardBtn) cardBtn.classList.toggle('is-fav', idx === -1);
        if (window.renderSkillFavs) window.renderSkillFavs();
    }

    function getFeatureState(skillId) { return _features[skillId] || {}; }

    window.SkillsExpanded = {
        open: open, close: close,
        toggleFeature: toggleFeature, getFeatureState: getFeatureState,
        toggleFav: toggleFav, isFav: isFav, getFavs: getFavs
    };
})();
