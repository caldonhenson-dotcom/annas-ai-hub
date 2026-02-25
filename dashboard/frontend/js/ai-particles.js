/* ============================================================
   AI Particles — quantum/vector background for Anna section
   ============================================================ */
(function () {
    'use strict';

    var canvas, ctx, particles, connections, raf;
    var running = false;
    var PARTICLE_COUNT = 60;
    var CONNECTION_DIST = 120;
    var SPEED = 0.3;
    var ACCENT_R = 60, ACCENT_G = 180, ACCENT_B = 173;
    var BLUE_R = 51, BLUE_G = 79, BLUE_B = 180;

    function init() {
        canvas = document.getElementById('ai-particles-canvas');
        if (!canvas) return;
        ctx = canvas.getContext('2d');
        resize();
        createParticles();
        if (!running) { running = true; animate(); }
    }

    function resize() {
        if (!canvas) return;
        var rect = canvas.parentElement.getBoundingClientRect();
        canvas.width = rect.width;
        canvas.height = rect.height;
    }

    function createParticles() {
        particles = [];
        if (!canvas) return;
        for (var i = 0; i < PARTICLE_COUNT; i++) {
            particles.push({
                x: Math.random() * canvas.width,
                y: Math.random() * canvas.height,
                vx: (Math.random() - 0.5) * SPEED,
                vy: (Math.random() - 0.5) * SPEED,
                r: Math.random() * 2 + 1,
                type: Math.random() > 0.5 ? 'accent' : 'blue',
                pulse: Math.random() * Math.PI * 2
            });
        }
    }

    function animate() {
        if (!running || !ctx || !canvas) return;

        // Respect reduced motion
        if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
            drawStatic();
            return;
        }

        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // Update and draw particles
        for (var i = 0; i < particles.length; i++) {
            var p = particles[i];
            p.x += p.vx;
            p.y += p.vy;
            p.pulse += 0.02;

            // Bounce off edges
            if (p.x < 0 || p.x > canvas.width) p.vx *= -1;
            if (p.y < 0 || p.y > canvas.height) p.vy *= -1;
            p.x = Math.max(0, Math.min(canvas.width, p.x));
            p.y = Math.max(0, Math.min(canvas.height, p.y));

            // Pulsing opacity
            var alpha = 0.3 + Math.sin(p.pulse) * 0.15;
            var r, g, b;
            if (p.type === 'accent') { r = ACCENT_R; g = ACCENT_G; b = ACCENT_B; }
            else { r = BLUE_R; g = BLUE_G; b = BLUE_B; }

            // Glow effect
            ctx.beginPath();
            var grad = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.r * 4);
            grad.addColorStop(0, 'rgba(' + r + ',' + g + ',' + b + ',' + (alpha * 0.5) + ')');
            grad.addColorStop(1, 'rgba(' + r + ',' + g + ',' + b + ',0)');
            ctx.fillStyle = grad;
            ctx.arc(p.x, p.y, p.r * 4, 0, Math.PI * 2);
            ctx.fill();

            // Core dot
            ctx.beginPath();
            ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(' + r + ',' + g + ',' + b + ',' + alpha + ')';
            ctx.fill();
        }

        // Draw connections
        drawConnections();

        raf = requestAnimationFrame(animate);
    }

    function drawConnections() {
        for (var i = 0; i < particles.length; i++) {
            for (var j = i + 1; j < particles.length; j++) {
                var dx = particles[i].x - particles[j].x;
                var dy = particles[i].y - particles[j].y;
                var dist = Math.sqrt(dx * dx + dy * dy);
                if (dist < CONNECTION_DIST) {
                    var alpha = (1 - dist / CONNECTION_DIST) * 0.12;
                    ctx.beginPath();
                    ctx.moveTo(particles[i].x, particles[i].y);
                    ctx.lineTo(particles[j].x, particles[j].y);
                    ctx.strokeStyle = 'rgba(' + ACCENT_R + ',' + ACCENT_G + ',' + ACCENT_B + ',' + alpha + ')';
                    ctx.lineWidth = 0.5;
                    ctx.stroke();
                }
            }
        }
    }

    function drawStatic() {
        if (!ctx || !canvas) return;
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        for (var i = 0; i < particles.length; i++) {
            var p = particles[i];
            var r, g, b;
            if (p.type === 'accent') { r = ACCENT_R; g = ACCENT_G; b = ACCENT_B; }
            else { r = BLUE_R; g = BLUE_G; b = BLUE_B; }
            ctx.beginPath();
            ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(' + r + ',' + g + ',' + b + ',0.25)';
            ctx.fill();
        }
        drawConnections();
    }

    function stop() {
        running = false;
        if (raf) cancelAnimationFrame(raf);
    }

    function start() {
        if (!canvas) init();
        if (!running) { running = true; animate(); }
    }

    // Resize handler
    var resizeTimer;
    window.addEventListener('resize', function () {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(function () {
            resize();
            if (particles) {
                particles.forEach(function (p) {
                    if (p.x > canvas.width) p.x = canvas.width * Math.random();
                    if (p.y > canvas.height) p.y = canvas.height * Math.random();
                });
            }
        }, 200);
    });

    window.AIParticles = { init: init, start: start, stop: stop };
})();
