/* ============================================================
   Monday IC Board — stage filter, detail panel toggle
   ============================================================ */
(function () {
    'use strict';

    // Toggle IC project detail panel (accordion)
    window.toggleICDetail = function (id) {
        var el = document.getElementById(id);
        var arrow = document.getElementById(id + '_arrow');
        if (!el) return;
        // Close all other open details
        document.querySelectorAll('.ic-detail.open').forEach(function (d) {
            if (d.id !== id) {
                d.classList.remove('open');
                var otherArrow = document.getElementById(d.id + '_arrow');
                if (otherArrow) otherArrow.classList.remove('open');
            }
        });
        el.classList.toggle('open');
        if (arrow) arrow.classList.toggle('open');
    };

    // Stage counts and filter logic
    var icStageCounts = { "due diligence": 1, "negotiation": 5, "screening": 12, "passed": 1, "completed": 1 };
    icStageCounts['all'] = 20;

    // Populate stage count badges
    document.querySelectorAll('[data-stage-count]').forEach(function (el) {
        var stage = el.getAttribute('data-stage-count');
        var count = icStageCounts[stage] || 0;
        if (stage === 'all') count = icStageCounts['all'];
        el.textContent = count > 0 ? '(' + count + ')' : '';
    });

    var currentICFilter = 'all';

    window.filterICStage = function (stage) {
        currentICFilter = stage;
        var rows = document.querySelectorAll('.ic-row');
        var visibleCount = 0;

        // When filtering, expand all rows (override show-10 limit)
        if (stage !== 'all') {
            rows.forEach(function (row) {
                if (row.classList.contains('ic-extra-row')) {
                    row.style.display = '';
                }
            });
        }

        rows.forEach(function (row) {
            var rowStage = row.getAttribute('data-ic-stage');
            var match = (stage === 'all' || rowStage === stage);
            if (match) {
                row.style.display = '';
                visibleCount++;
            } else {
                row.style.display = 'none';
            }
        });

        // If "all" is selected, re-apply the show-10 limit
        if (stage === 'all') {
            rows.forEach(function (row) {
                if (row.classList.contains('ic-extra-row')) {
                    var expandBtn = document.getElementById('ic-show-more');
                    var isExpanded = expandBtn && expandBtn.getAttribute('data-expanded') === '1';
                    if (!isExpanded) {
                        row.style.display = 'none';
                    }
                }
            });
        }

        // Hide show-more button when filtering
        var moreBtn = document.getElementById('ic-show-more');
        if (moreBtn) {
            moreBtn.parentElement.style.display = (stage === 'all') ? '' : 'none';
        }

        // Update active button styling
        document.querySelectorAll('.ic-stage-btn').forEach(function (btn) {
            var btnStage = btn.getAttribute('data-ic-filter');
            if (btnStage === stage) {
                btn.classList.add('ic-stage-active');
                btn.style.background = '#3CB4AD';
                btn.style.color = '#fff';
                btn.style.borderColor = '#3CB4AD';
                btn.style.boxShadow = '0 2px 8px rgba(60,180,173,0.25)';
            } else {
                btn.classList.remove('ic-stage-active');
                btn.style.background = '#ffffff';
                btn.style.color = '#6b7280';
                btn.style.borderColor = '#e2e5ea';
                btn.style.boxShadow = 'none';
            }
        });

        // Update filter status text
        var statusEl = document.getElementById('ic-filter-status');
        if (statusEl) {
            if (stage === 'all') {
                statusEl.textContent = '';
            } else {
                var label = stage.charAt(0).toUpperCase() + stage.slice(1);
                statusEl.textContent = 'Showing: ' + label + ' (' + visibleCount + ')';
            }
        }
    };

    // Set "All" as active on page load
    var allBtn = document.querySelector('.ic-stage-btn.ic-stage-active');
    if (allBtn) {
        allBtn.style.background = '#3CB4AD';
        allBtn.style.color = '#fff';
        allBtn.style.borderColor = '#3CB4AD';
        allBtn.style.boxShadow = '0 2px 8px rgba(60,180,173,0.25)';
    }
})();
