/* ============================================================
   Charts — Chart.js bar/line + CSS progress bars
   ============================================================ */
(function () {
    'use strict';

    var instances = {};
    var MONTH_SHORT = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

    // Chart.js global defaults
    if (window.Chart) {
        Chart.defaults.font.family = '"Assistant", sans-serif';
        Chart.defaults.animation.duration = 800;
        Chart.defaults.animation.easing = 'easeOutQuart';
    }

    // ------------------------------------------------------------------
    // Helper: get or create a <canvas> inside a container div
    // ------------------------------------------------------------------
    function getCanvas(containerId) {
        var container = document.getElementById(containerId);
        if (!container) return null;
        var canvas = container.querySelector('canvas');
        if (!canvas) {
            container.innerHTML = '';
            container.style.position = 'relative';
            container.style.height = container.style.height || '120px';
            canvas = document.createElement('canvas');
            container.appendChild(canvas);
        }
        return canvas;
    }

    // ------------------------------------------------------------------
    // Mini Bar — CSS horizontal progress bars with labels (not Chart.js)
    // ------------------------------------------------------------------
    function renderMiniBar(containerId, data, maxItems) {
        var el = document.getElementById(containerId);
        if (!el) return;
        maxItems = maxItems || 8;
        var sorted = Object.entries(data).sort(function (a, b) { return b[1] - a[1]; }).slice(0, maxItems);
        if (sorted.length === 0) {
            el.innerHTML = '<div style="text-align:center;padding:20px;color:#6b7280;font-size:13px">No data for this period</div>';
            return;
        }
        var maxVal = sorted[0][1] || 1;
        var palette = ['#3CB4AD','#334FB4','#a78bfa','#34d399','#f472b6','#f59e0b','#60a5fa','#ef4444'];
        var html = '';
        sorted.forEach(function (item, i) {
            var label = item[0].length > 20 ? item[0].substring(0, 18) + '..' : item[0];
            var val = item[1];
            var pct = Math.max(2, (val / maxVal) * 100);
            var color = palette[i % palette.length];
            html += '<div style="margin-bottom:5px">'
                + '<div style="display:flex;justify-content:space-between;margin-bottom:3px;font-size:12px">'
                + '<span style="color:#6b7280">' + label + '</span>'
                + '<span style="color:#121212;font-weight:600">' + fmtNum(val) + '</span></div>'
                + '<div style="height:6px;background:#e5e7eb;border-radius:3px;overflow:hidden">'
                + '<div style="height:100%;width:' + pct.toFixed(1) + '%;background:' + color
                + ';border-radius:3px;transition:width 0.6s cubic-bezier(.25,.1,.25,1)"></div></div></div>';
        });
        el.innerHTML = html;
    }

    // ------------------------------------------------------------------
    // Monthly Bar Chart — Chart.js bar with tooltips & hover
    // ------------------------------------------------------------------
    function renderMonthlyBarChart(containerId, data, color, isCurrency) {
        var canvas = getCanvas(containerId);
        if (!canvas) return;

        var entries = Object.entries(data).sort();
        if (entries.length > 6) entries = entries.slice(entries.length - 6);
        if (entries.length === 0) {
            canvas.parentElement.innerHTML = '<span style="color:#64748b;font-size:11px">No data</span>';
            delete instances[containerId];
            return;
        }

        var labels = entries.map(function (e) {
            var parts = e[0].split('-');
            return MONTH_SHORT[parseInt(parts[1], 10) - 1] || e[0];
        });
        var values = entries.map(function (e) { return e[1]; });

        // Update existing chart or create new
        if (instances[containerId]) {
            var chart = instances[containerId];
            chart.data.labels = labels;
            chart.data.datasets[0].data = values;
            chart.data.datasets[0].backgroundColor = color + 'CC';
            chart.data.datasets[0].borderColor = color;
            chart.update();
            return;
        }

        instances[containerId] = new Chart(canvas, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    data: values,
                    backgroundColor: color + 'CC',
                    hoverBackgroundColor: color,
                    borderColor: color,
                    borderWidth: 1,
                    borderRadius: 4,
                    barPercentage: 0.7
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: '#242833',
                        titleFont: { weight: '600' },
                        bodyFont: { size: 13 },
                        padding: 10,
                        cornerRadius: 8,
                        callbacks: {
                            label: function (ctx) {
                                var v = ctx.raw;
                                return isCurrency ? '\u00a3' + v.toLocaleString('en-GB') : v.toLocaleString('en-GB');
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        display: false,
                        beginAtZero: true
                    },
                    x: {
                        grid: { display: false },
                        border: { display: false },
                        ticks: {
                            font: { size: 11, weight: '600' },
                            color: '#94a3b8'
                        }
                    }
                }
            }
        });
    }

    // ------------------------------------------------------------------
    // Sparkline — Chart.js line (compact, no axes)
    // ------------------------------------------------------------------
    function renderSparkline(containerId, data, color) {
        var canvas = getCanvas(containerId);
        if (!canvas) return;
        color = color || '#3CB4AD';

        var entries = Object.entries(data).sort();
        if (entries.length < 2) {
            canvas.parentElement.innerHTML = '';
            delete instances[containerId];
            return;
        }

        var labels = entries.map(function (e) { return e[0]; });
        var values = entries.map(function (e) { return e[1]; });

        if (instances[containerId]) {
            var chart = instances[containerId];
            chart.data.labels = labels;
            chart.data.datasets[0].data = values;
            chart.update();
            return;
        }

        // Set compact height for sparklines
        canvas.parentElement.style.height = '40px';

        instances[containerId] = new Chart(canvas, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    data: values,
                    borderColor: color,
                    borderWidth: 2,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                    pointHoverBackgroundColor: color,
                    fill: true,
                    backgroundColor: color + '20',
                    tension: 0.3
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: '#242833',
                        cornerRadius: 6,
                        padding: 8,
                        bodyFont: { size: 12 }
                    }
                },
                scales: {
                    x: { display: false },
                    y: { display: false }
                }
            }
        });
    }

    window.renderMiniBar = renderMiniBar;
    window.renderSparkline = renderSparkline;
    window.renderMonthlyBarChart = renderMonthlyBarChart;
})();
