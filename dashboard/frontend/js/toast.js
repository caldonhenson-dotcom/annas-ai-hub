/* ============================================================
   Toast Notification System
   ============================================================ */
(function () {
    'use strict';

    var container = null;
    var ICONS = {
        success: '\u2705',
        error: '\u274C',
        warning: '\u26A0\uFE0F',
        info: '\u2139\uFE0F'
    };

    function getContainer() {
        if (!container) {
            container = document.createElement('div');
            container.className = 'toast-container';
            container.setAttribute('aria-live', 'polite');
            container.setAttribute('aria-atomic', 'false');
            document.body.appendChild(container);
        }
        return container;
    }

    function show(message, variant, duration) {
        variant = variant || 'info';
        duration = (typeof duration === 'number') ? duration : 4000;

        var toast = document.createElement('div');
        toast.className = 'toast toast--' + variant;
        toast.setAttribute('role', 'alert');

        toast.innerHTML =
            '<span class="toast-icon">' + (ICONS[variant] || '') + '</span>' +
            '<span class="toast-message">' + message + '</span>' +
            '<button class="toast-dismiss" aria-label="Dismiss">&times;</button>' +
            '<div class="toast-progress" style="animation:toast-countdown ' + duration + 'ms linear forwards"></div>';

        var dismiss = toast.querySelector('.toast-dismiss');
        dismiss.addEventListener('click', function () { remove(toast); });

        getContainer().appendChild(toast);

        var timer = setTimeout(function () { remove(toast); }, duration);
        toast._timer = timer;

        return toast;
    }

    function remove(toast) {
        if (toast._removed) return;
        toast._removed = true;
        clearTimeout(toast._timer);
        toast.classList.add('removing');
        toast.addEventListener('animationend', function () {
            if (toast.parentNode) toast.parentNode.removeChild(toast);
        });
    }

    // Add progress countdown keyframe if not present
    if (!document.getElementById('toast-keyframes')) {
        var style = document.createElement('style');
        style.id = 'toast-keyframes';
        style.textContent = '@keyframes toast-countdown { from { width: 100%; } to { width: 0%; } }';
        document.head.appendChild(style);
    }

    window.Toast = {
        show: show,
        success: function (msg, dur) { return show(msg, 'success', dur); },
        error: function (msg, dur) { return show(msg, 'error', dur); },
        warning: function (msg, dur) { return show(msg, 'warning', dur); },
        info: function (msg, dur) { return show(msg, 'info', dur); }
    };
})();
