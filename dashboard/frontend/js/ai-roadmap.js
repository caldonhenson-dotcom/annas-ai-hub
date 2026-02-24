/* ============================================================
   AI Roadmap — detail panel toggle
   ============================================================ */
window.toggleAIDetail = function (id) {
    var el = document.getElementById(id);
    if (!el) return;
    document.querySelectorAll('.ai-item-detail.open').forEach(function (d) {
        if (d.id !== id) d.classList.remove('open');
    });
    el.classList.toggle('open');
};
