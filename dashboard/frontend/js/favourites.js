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

    // Initial render
    renderFavs();
})();
