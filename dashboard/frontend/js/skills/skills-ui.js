/* ============================================================
   Skills UI — cards grid, execution modal, progress, results
   ============================================================ */
(function () {
    'use strict';

    var _activeCategory = null;
    var _searchQuery = '';
    var _currentSkillId = null;

    function esc(s) { var d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

    // ------------------------------------------------------------------
    // Main renderer (called by router after scripts load)
    // ------------------------------------------------------------------
    window.renderSkills = function () {
        renderStatsRow();
        renderCategoryPills();
        renderGrid(getFilteredSkills());
        if (window.ConnectorsUI) window.ConnectorsUI.render();
        if (window.Connectors) window.Connectors.checkAll();
        if (window.renderSkillFavs) window.renderSkillFavs();
        document.addEventListener('skill-progress', onProgress);
    };

    // ------------------------------------------------------------------
    // Stats row
    // ------------------------------------------------------------------
    function renderStatsRow() {
        var el = document.getElementById('skills-stats-row');
        if (!el) return;
        var s = window.SkillsRegistry.getStats();
        var saved = window.SkillsRegistry.getTotalTimeSaved();
        el.innerHTML = ''
            + statPill('Total Skills', s.total, '#3CB4AD')
            + statPill('Ready', s.ready, '#16a34a')
            + statPill('Categories', Object.keys(window.SkillsRegistry.CATEGORIES).length, '#8b5cf6')
            + statPill('Time Saved Today', saved + ' min', '#f59e0b');
    }

    function statPill(label, value, color) {
        return '<div class="skill-stat-pill">'
            + '<div class="skill-stat-value" style="color:' + color + '">' + value + '</div>'
            + '<div class="skill-stat-label">' + esc(label) + '</div></div>';
    }

    // ------------------------------------------------------------------
    // Category pills
    // ------------------------------------------------------------------
    function renderCategoryPills() {
        var el = document.getElementById('skills-category-pills');
        if (!el) return;
        var cats = window.SkillsRegistry.getCategories();
        var html = '<button class="skill-cat-pill active" onclick="window.SkillsUI.filterCategory(null)">All</button>';
        for (var key in cats) {
            var c = cats[key];
            html += '<button class="skill-cat-pill" data-cat="' + key + '" '
                + 'onclick="window.SkillsUI.filterCategory(\'' + key + '\')">'
                + '<span>' + c.icon + '</span> ' + esc(c.name) + '</button>';
        }
        el.innerHTML = html;
    }

    // ------------------------------------------------------------------
    // Grid rendering
    // ------------------------------------------------------------------
    function getFilteredSkills() {
        var skills = _activeCategory
            ? window.SkillsRegistry.getByCategory(_activeCategory)
            : window.SkillsRegistry.getAll();
        if (_searchQuery) {
            skills = window.SkillsRegistry.search(_searchQuery);
            if (_activeCategory) {
                skills = skills.filter(function (s) { return s.category === _activeCategory; });
            }
        }
        return skills.sort(function (a, b) { return (b.impact || 0) - (a.impact || 0); });
    }

    function renderGrid(skills) {
        var el = document.getElementById('skills-grid');
        if (!el) return;
        if (skills.length === 0) {
            el.innerHTML = '<div class="skills-empty">No skills match your search.</div>';
            return;
        }
        el.innerHTML = skills.map(skillCard).join('');
    }

    function skillCard(skill) {
        var cats = window.SkillsRegistry.CATEGORIES;
        var cat = cats[skill.category] || {};
        var stars = '';
        for (var i = 1; i <= 5; i++) stars += '<span class="skill-star' + (i <= skill.impact ? ' filled' : '') + '">&#9733;</span>';
        var statusCls = skill.status === 'ready' ? 'ready' : (skill.status === 'partial' ? 'partial' : 'planned');
        var fav = window.SkillsExpanded && window.SkillsExpanded.isFav(skill.id);
        return '<div class="skill-card" data-skill-id="' + skill.id + '" '
            + 'onclick="if(window.SkillsExpanded)window.SkillsExpanded.open(\'' + skill.id + '\')">'
            + '<div class="skill-card-header">'
            + '<span class="skill-card-icon" style="color:' + (cat.color || '#6b7280') + '">' + (skill.icon || cat.icon || '') + '</span>'
            + '<button class="skill-fav-btn' + (fav ? ' is-fav' : '') + '" '
            + 'onclick="event.stopPropagation();if(window.SkillsExpanded)window.SkillsExpanded.toggleFav(\'' + skill.id + '\')">&#9733;</button>'
            + '<span class="skill-status-badge ' + statusCls + '">' + esc(skill.status) + '</span>'
            + '</div>'
            + '<div class="skill-card-name">' + esc(skill.name) + '</div>'
            + '<div class="skill-card-desc">' + esc(skill.description) + '</div>'
            + '<div class="skill-card-meta">'
            + '<span class="skill-card-stars">' + stars + '</span>'
            + '<span class="skill-card-time">' + esc(skill.estimatedTime || '') + '</span>'
            + '</div>'
            + '<div class="skill-card-cat" style="color:' + (cat.color || '#6b7280') + '">' + (cat.icon || '') + ' ' + esc(cat.name || '') + '</div>'
            + '<button class="skill-exec-btn" onclick="event.stopPropagation();window.SkillsUI.openExecModal(\'' + skill.id + '\')"'
            + (skill.status !== 'ready' ? ' disabled title="Not yet available"' : '')
            + '>&#9889; Execute</button>'
            + '</div>';
    }

    // ------------------------------------------------------------------
    // Execution modal
    // ------------------------------------------------------------------
    function openExecModal(skillId) {
        var skill = window.SkillsRegistry.get(skillId);
        if (!skill) return;
        _currentSkillId = skillId;
        var overlay = document.getElementById('skill-exec-overlay');
        var header = document.getElementById('skill-exec-header');
        var inputs = document.getElementById('skill-exec-inputs');
        var actions = document.getElementById('skill-exec-actions');
        var progress = document.getElementById('skill-exec-progress');
        var result = document.getElementById('skill-exec-result');

        header.innerHTML = '<div class="skill-exec-icon">' + (skill.icon || '') + '</div>'
            + '<div><div class="skill-exec-title">' + esc(skill.name) + '</div>'
            + '<div class="skill-exec-desc">' + esc(skill.description) + '</div></div>';
        inputs.innerHTML = renderInputForm(skill.execute.inputs || []);
        actions.innerHTML = '<button class="skill-run-btn" onclick="window.SkillsUI.onExecute()">'
            + '&#9889; Run Skill</button>'
            + '<button class="skill-cancel-btn" onclick="window.SkillsUI.closeExecModal()">Cancel</button>';
        progress.classList.add('hidden');
        progress.innerHTML = '';
        result.classList.add('hidden');
        result.innerHTML = '';
        overlay.classList.remove('hidden');
    }

    function closeExecModal() {
        var overlay = document.getElementById('skill-exec-overlay');
        if (overlay) overlay.classList.add('hidden');
        if (_currentSkillId && window.SkillsEngine.isRunning(_currentSkillId)) {
            window.SkillsEngine.cancel(_currentSkillId);
        }
        _currentSkillId = null;
    }

    function renderInputForm(inputDefs) {
        if (!inputDefs || inputDefs.length === 0) return '<p class="skill-no-inputs">No configuration needed — click Run to execute.</p>';
        return inputDefs.map(function (inp) {
            var html = '<div class="skill-input-group"><label class="skill-input-label">'
                + esc(inp.label) + (inp.required ? ' *' : '') + '</label>';
            switch (inp.type) {
                case 'select':
                    html += '<select class="skill-input" data-key="' + inp.key + '">';
                    (inp.options || []).forEach(function (opt) {
                        html += '<option value="' + esc(opt.value) + '"' + (opt.value === inp.default ? ' selected' : '') + '>'
                            + esc(opt.label) + '</option>';
                    });
                    html += '</select>';
                    break;
                case 'textarea':
                    html += '<textarea class="skill-input skill-textarea" data-key="' + inp.key + '" '
                        + 'placeholder="' + esc(inp.placeholder || '') + '">' + esc(inp.default || '') + '</textarea>';
                    break;
                default:
                    html += '<input type="' + (inp.type || 'text') + '" class="skill-input" data-key="' + inp.key + '" '
                        + 'placeholder="' + esc(inp.placeholder || '') + '" value="' + esc(inp.default || '') + '" />';
            }
            return html + '</div>';
        }).join('');
    }

    // ------------------------------------------------------------------
    // Execute from modal
    // ------------------------------------------------------------------
    function onExecute() {
        if (!_currentSkillId) return;
        var vals = {};
        document.querySelectorAll('#skill-exec-inputs .skill-input').forEach(function (el) {
            vals[el.getAttribute('data-key')] = el.value;
        });
        var actions = document.getElementById('skill-exec-actions');
        actions.innerHTML = '<button class="skill-cancel-btn" onclick="window.SkillsEngine.cancel(\'' + _currentSkillId + '\')">&#10005; Cancel</button>';
        window.SkillsEngine.execute(_currentSkillId, vals)
            .then(function (res) { renderResult(res); })
            .catch(function () { /* progress event handles error display */ });
    }

    // ------------------------------------------------------------------
    // Progress listener
    // ------------------------------------------------------------------
    function onProgress(e) {
        var d = e.detail;
        if (d.skillId !== _currentSkillId) return;
        var progress = document.getElementById('skill-exec-progress');
        if (!progress) return;
        progress.classList.remove('hidden');
        if (d.status === 'running') {
            progress.innerHTML = '<div class="skill-spinner"></div><span>' + esc(d.message) + '</span>';
        } else if (d.status === 'complete') {
            progress.innerHTML = '<span class="skill-done-icon">&#10003;</span><span>' + esc(d.message) + '</span>';
        } else if (d.status === 'error') {
            progress.innerHTML = '<span class="skill-error-icon">&#10007;</span><span>Error: ' + esc(d.message) + '</span>'
                + '<button class="skill-retry-btn" onclick="window.SkillsUI.onExecute()">Retry</button>';
        }
    }

    // ------------------------------------------------------------------
    // Result rendering
    // ------------------------------------------------------------------
    function renderResult(res) {
        var el = document.getElementById('skill-exec-result');
        if (!el) return;
        el.classList.remove('hidden');
        var skill = window.SkillsRegistry.get(_currentSkillId);
        var content = '';
        if (res.type === 'markdown' || res.type === 'text') {
            content = '<div class="skill-result-text">' + formatMarkdown(typeof res.data === 'string' ? res.data : JSON.stringify(res.data)) + '</div>';
        } else if (res.type === 'draft') {
            content = '<textarea class="skill-result-draft">' + esc(typeof res.data === 'string' ? res.data : JSON.stringify(res.data)) + '</textarea>';
        } else {
            content = '<pre class="skill-result-json">' + esc(JSON.stringify(res.data, null, 2)) + '</pre>';
        }
        var btns = (res.actions || []).map(function (a) {
            return '<button class="skill-action-btn" onclick="window.SkillsEngine.handleResultAction(\'' + a.handler + '\',window.SkillsRegistry.get(\'' + _currentSkillId + '\'),window._lastSkillResult)">' + a.label + '</button>';
        }).join('');
        el.innerHTML = content + (btns ? '<div class="skill-result-actions">' + btns + '</div>' : '');
        window._lastSkillResult = res;
    }

    function formatMarkdown(text) {
        return text
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.+?)\*/g, '<em>$1</em>')
            .replace(/^### (.+)$/gm, '<h4>$1</h4>')
            .replace(/^## (.+)$/gm, '<h3>$1</h3>')
            .replace(/^# (.+)$/gm, '<h2>$1</h2>')
            .replace(/^- (.+)$/gm, '<li>$1</li>')
            .replace(/\n/g, '<br>');
    }

    // ------------------------------------------------------------------
    // Search + filter
    // ------------------------------------------------------------------
    window.SkillsUI = {
        onSearch: function (q) { _searchQuery = q; renderGrid(getFilteredSkills()); },
        filterCategory: function (catId) {
            _activeCategory = catId;
            document.querySelectorAll('.skill-cat-pill').forEach(function (btn) {
                btn.classList.toggle('active', catId === null ? !btn.dataset.cat : btn.dataset.cat === catId);
            });
            renderGrid(getFilteredSkills());
        },
        openExecModal: openExecModal,
        closeExecModal: closeExecModal,
        onExecute: onExecute
    };
})();
