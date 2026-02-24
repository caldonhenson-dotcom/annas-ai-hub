/* ============================================================
   Monday Pipeline Board — filter, group toggle, expand lists
   ============================================================ */
(function () {
    'use strict';

    // Populate owner/stage filter dropdowns from board data
    var rows = document.querySelectorAll('.monday-row');
    var owners = new Set(), stages = new Set();
    rows.forEach(function (r) {
        var o = r.getAttribute('data-owner');
        var s = r.getAttribute('data-stage');
        if (o && o !== 'Unassigned') owners.add(o);
        if (s) stages.add(s);
    });
    var ownerSel = document.getElementById('monday-filter-owner');
    var stageSel = document.getElementById('monday-filter-stage');
    if (ownerSel) {
        Array.from(owners).sort().forEach(function (o) {
            var opt = document.createElement('option');
            opt.value = o; opt.textContent = o;
            ownerSel.appendChild(opt);
        });
    }
    if (stageSel) {
        Array.from(stages).sort().forEach(function (s) {
            var opt = document.createElement('option');
            opt.value = s;
            opt.textContent = s.replace(/_/g, ' ').replace(/\b\w/g, function (l) { return l.toUpperCase(); });
            stageSel.appendChild(opt);
        });
    }

    // Filter pipeline rows by search, owner, stage, unassigned
    window.filterMonday = function () {
        var q = (document.getElementById('monday-search').value || '').toLowerCase();
        var owner = document.getElementById('monday-filter-owner').value;
        var stage = document.getElementById('monday-filter-stage').value;
        var hideUnassigned = document.getElementById('monday-hide-unassigned').checked;
        var allRows = document.querySelectorAll('.monday-row');
        var visible = 0;
        allRows.forEach(function (r) {
            var show = true;
            if (q) {
                var text = (r.getAttribute('data-name') || '') + ' ' +
                    (r.getAttribute('data-owner') || '') + ' ' +
                    (r.getAttribute('data-ws') || '') + ' ' +
                    (r.getAttribute('data-stage') || '');
                if (text.toLowerCase().indexOf(q) === -1) show = false;
            }
            if (owner && r.getAttribute('data-owner') !== owner) show = false;
            if (stage && r.getAttribute('data-stage') !== stage) show = false;
            if (hideUnassigned && r.getAttribute('data-has-owner') === '0') show = false;
            r.style.display = show ? '' : 'none';
            if (show) visible++;
        });
        var countEl = document.getElementById('monday-count');
        if (countEl) countEl.textContent = '(' + visible + ')';
    };

    // Toggle board group visibility (shared with IC)
    window.toggleBoardGroup = function (id) {
        var el = document.getElementById(id);
        var arrow = document.getElementById(id + '_arrow');
        if (!el) return;
        if (el.style.display === 'none') {
            el.style.display = 'block';
            if (arrow) arrow.classList.add('expanded');
        } else {
            el.style.display = 'none';
            if (arrow) arrow.classList.remove('expanded');
        }
    };

    // Show-more / show-less expand toggle
    window.toggleExpandList = function (extraClass, btnId, total, limit) {
        var extras = document.querySelectorAll('.' + extraClass);
        var btn = document.getElementById(btnId);
        if (!btn) return;
        var isExpanded = btn.getAttribute('data-expanded') === '1';
        extras.forEach(function (el) {
            el.style.display = isExpanded ? 'none' : '';
        });
        if (isExpanded) {
            btn.textContent = 'Show all ' + total + ' (' + (total - limit) + ' more)';
            btn.setAttribute('data-expanded', '0');
        } else {
            btn.textContent = 'Show less (collapse to ' + limit + ')';
            btn.setAttribute('data-expanded', '1');
        }
    };
})();
