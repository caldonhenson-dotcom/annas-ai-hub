/* ============================================================
   Animations — countUp numbers + staggered card entry
   ============================================================ */
(function () {
    'use strict';

    // Respect reduced motion preference
    var prefersReduced = window.matchMedia
        && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    // ------------------------------------------------------------------
    // countUp — animate a number from 0 to target
    // ------------------------------------------------------------------
    function countUp(el, target, duration, opts) {
        if (prefersReduced) {
            el.textContent = formatValue(target, opts);
            return;
        }
        opts = opts || {};
        duration = duration || 800;
        var prefix = opts.prefix || '';
        var suffix = opts.suffix || '';
        var decimals = opts.decimals || 0;
        var start = 0;
        var startTime = null;

        function formatValue(val, o) {
            o = o || opts;
            var p = o.prefix || '';
            var s = o.suffix || '';
            var d = o.decimals || 0;
            var num = d > 0 ? val.toFixed(d) : Math.round(val);
            if (o.separator !== false) {
                num = Number(num).toLocaleString('en-GB', {
                    minimumFractionDigits: d,
                    maximumFractionDigits: d
                });
            }
            return p + num + s;
        }

        function easeOutQuart(t) {
            return 1 - Math.pow(1 - t, 4);
        }

        function step(ts) {
            if (!startTime) startTime = ts;
            var progress = Math.min((ts - startTime) / duration, 1);
            var eased = easeOutQuart(progress);
            var current = start + (target - start) * eased;
            el.textContent = formatValue(current, opts);
            if (progress < 1) requestAnimationFrame(step);
        }

        requestAnimationFrame(step);
    }

    // ------------------------------------------------------------------
    // Auto-apply countUp to elements with data-count-up attribute
    // ------------------------------------------------------------------
    function initCountUps(container) {
        if (prefersReduced) return;
        var els = (container || document).querySelectorAll('[data-count-up]');
        els.forEach(function (el) {
            if (el.dataset.counted) return;
            var target = parseFloat(el.dataset.countUp);
            if (isNaN(target)) return;
            var opts = {};
            if (el.dataset.prefix) opts.prefix = el.dataset.prefix;
            if (el.dataset.suffix) opts.suffix = el.dataset.suffix;
            if (el.dataset.decimals) opts.decimals = parseInt(el.dataset.decimals, 10);
            el.dataset.counted = '1';
            countUp(el, target, 800, opts);
        });
    }

    // ------------------------------------------------------------------
    // staggerCards — animate cards into view with staggered delay
    // ------------------------------------------------------------------
    function staggerCards(container) {
        if (prefersReduced) return;
        if (!container) return;

        var cards = container.querySelectorAll('.glass-card, .stat-card, .exec-pillar, .exec-kpi');
        if (cards.length === 0) return;

        cards.forEach(function (card, i) {
            card.style.opacity = '0';
            card.style.transform = 'translateY(12px)';
            card.style.transition = 'none';

            setTimeout(function () {
                card.style.transition = 'opacity 0.35s ease-out, transform 0.35s ease-out';
                card.style.opacity = '1';
                card.style.transform = 'translateY(0)';
            }, 40 * i);
        });
    }

    // ------------------------------------------------------------------
    // IntersectionObserver — animate cards when scrolled into view
    // ------------------------------------------------------------------
    var observer = null;
    if (!prefersReduced && window.IntersectionObserver) {
        observer = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (entry.isIntersecting) {
                    var el = entry.target;
                    el.style.transition = 'opacity 0.35s ease-out, transform 0.35s ease-out';
                    el.style.opacity = '1';
                    el.style.transform = 'translateY(0)';
                    observer.unobserve(el);
                }
            });
        }, { threshold: 0.1 });
    }

    function observeCards(container) {
        if (!observer || prefersReduced) return;
        var cards = (container || document).querySelectorAll('.glass-card, .stat-card');
        cards.forEach(function (card) {
            if (card.dataset.observed) return;
            card.dataset.observed = '1';
            card.style.opacity = '0';
            card.style.transform = 'translateY(12px)';
            observer.observe(card);
        });
    }

    // Expose globally
    window.countUp = countUp;
    window.staggerCards = staggerCards;
    window.initCountUps = initCountUps;
    window.observeCards = observeCards;
})();
