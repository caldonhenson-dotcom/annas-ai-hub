/* ============================================================
   Skills Expanded — detail card, blocks view, skill favourites
   ============================================================ */
(function () {
    'use strict';

    var _expandedId = null;
    var _features = {};

    function esc(s) { var d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

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
        // Initialise feature toggles from defaults
        if (!_features[skillId] && skill.features) {
            _features[skillId] = {};
            skill.features.forEach(function (f) { _features[skillId][f.id] = f.default !== false; });
        }
        var body = document.createElement('div');
        body.className = 'skill-expanded-body';
        body.innerHTML = blocksHtml(skill) + featuresHtml(skill) + actionsHtml(skill);
        card.appendChild(body);
        // Scroll expanded card into view
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
    // Actions row
    // ------------------------------------------------------------------
    function actionsHtml(skill) {
        var fav = isFav(skill.id);
        var stars = '';
        for (var i = 1; i <= 5; i++) stars += '<span class="skill-star' + (i <= skill.impact ? ' filled' : '') + '">&#9733;</span>';
        return '<div class="skill-expanded-actions">'
            + '<div class="skill-expanded-meta">'
            + stars
            + (skill.timeSaved ? ' &middot; Saves ~' + skill.timeSaved + 'min' : '')
            + (skill.estimatedTime ? ' &middot; Est: ' + esc(skill.estimatedTime) : '')
            + '</div>'
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
        // Update star in expanded card
        var expBtn = document.querySelector('.skill-expanded-actions .skill-fav-btn');
        if (expBtn) expBtn.classList.toggle('is-fav', idx === -1);
        // Update star on collapsed card header
        var cardBtn = document.querySelector('.skill-card[data-skill-id="' + skillId + '"] > .skill-card-header .skill-fav-btn');
        if (cardBtn) cardBtn.classList.toggle('is-fav', idx === -1);
        // Re-render sidebar
        if (window.renderSkillFavs) window.renderSkillFavs();
    }

    function getFeatureState(skillId) { return _features[skillId] || {}; }

    window.SkillsExpanded = {
        open: open,
        close: close,
        toggleFeature: toggleFeature,
        getFeatureState: getFeatureState,
        toggleFav: toggleFav,
        isFav: isFav,
        getFavs: getFavs
    };
})();
