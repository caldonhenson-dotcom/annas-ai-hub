/* ============================================================
   Favourites — sidebar star bookmarks
   ============================================================ */
(function () {
    'use strict';

    // Build module label map from sidebar links
    var MODULES_MAP = {};
    document.querySelectorAll('.sidebar-link[data-page]').forEach(function (link) {
        MODULES_MAP[link.getAttribute('data-page')] = link.textContent.trim();
    });

    function getFavs() {
        var prefs = window.loadPrefs();
        return Array.isArray(prefs.favs) ? prefs.favs : [];
    }

    function renderFavs() {
        var favs = getFavs();
        var container = document.getElementById('sidebar-favs');
        var list = document.getElementById('sidebar-favs-list');
        if (!container || !list) return;

        if (favs.length === 0) {
            container.classList.remove('has-favs');
            list.innerHTML = '';
            return;
        }
        container.classList.add('has-favs');

        var html = '';
        for (var i = 0; i < favs.length; i++) {
            var fid = favs[i];
            var label = MODULES_MAP[fid] || fid;
            html += '<a href="javascript:void(0)" onclick="showPage(\'' + fid + '\')" '
                + 'class="sidebar-link" data-page="' + fid + '">' + label
                + '<button class="sidebar-fav is-fav" data-fav="' + fid + '" '
                + 'onclick="event.preventDefault();event.stopPropagation();toggleFav(\'' + fid + '\')" '
                + 'title="Remove favourite">&#9733;</button></a>';
        }
        list.innerHTML = html;

        // Update star states in main nav
        document.querySelectorAll('.sidebar-fav[data-fav]').forEach(function (btn) {
            var pid = btn.getAttribute('data-fav');
            if (favs.indexOf(pid) !== -1) {
                btn.classList.add('is-fav');
            } else {
                btn.classList.remove('is-fav');
            }
        });
    }

    window.toggleFav = function (pageId) {
        var favs = getFavs();
        var idx = favs.indexOf(pageId);
        if (idx === -1) {
            favs.push(pageId);
        } else {
            favs.splice(idx, 1);
        }
        window.savePrefs({ favs: favs });
        renderFavs();
    };

    // ------------------------------------------------------------------
    // Skill favourites — sidebar "Quick Skills" section
    // ------------------------------------------------------------------
    function renderSkillFavs() {
        var prefs = window.loadPrefs ? window.loadPrefs() : {};
        var favs = Array.isArray(prefs.skillFavs) ? prefs.skillFavs : [];
        var container = document.getElementById('sidebar-skill-favs');
        var list = document.getElementById('sidebar-skill-favs-list');
        if (!container || !list) return;
        if (favs.length === 0) { container.style.display = 'none'; list.innerHTML = ''; return; }
        container.style.display = '';
        list.innerHTML = favs.map(function (f) {
            return '<a href="javascript:void(0)" class="sidebar-link" '
                + 'onclick="showPage(\'skills\');setTimeout(function(){if(window.SkillsUI)window.SkillsUI.openExecModal(\'' + f.id + '\')},500)">'
                + '<span>' + (f.icon || '&#9889;') + '</span> '
                + (f.name || f.id) + '</a>';
        }).join('');
    }
    window.renderSkillFavs = renderSkillFavs;

    // Initial render
    renderFavs();
    renderSkillFavs();
})();
