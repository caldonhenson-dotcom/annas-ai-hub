/* ============================================================
   Utilities — formatting, date ranges, escaping
   ============================================================ */
(function () {
    'use strict';

    function getDateRange(period) {
        var now = new Date();
        var y = now.getFullYear();
        var m = now.getMonth();
        var d = now.getDate();
        var day = now.getDay();
        var mondayOffset = day === 0 ? 6 : day - 1;
        var start, end;

        switch(period) {
            case 'this_week':
                start = new Date(y, m, d - mondayOffset);
                end = now;
                break;
            case 'last_week':
                start = new Date(y, m, d - mondayOffset - 7);
                end = new Date(y, m, d - mondayOffset - 1);
                break;
            case 'mtd':
                start = new Date(y, m, 1);
                end = now;
                break;
            case 'ytd':
                start = new Date(y, 0, 1);
                end = now;
                break;
            case 'last_year':
                start = new Date(y - 1, 0, 1);
                end = new Date(y - 1, 11, 31);
                break;
            case 'all':
            default:
                return null;
        }
        return {
            start: formatDate(start),
            end: formatDate(end)
        };
    }

    function formatDate(d) {
        var yy = d.getFullYear();
        var mm = String(d.getMonth() + 1).padStart(2, '0');
        var dd = String(d.getDate()).padStart(2, '0');
        return yy + '-' + mm + '-' + dd;
    }

    function sumDaily(series, range) {
        if (!series) return 0;
        var total = 0;
        for (var key in series) {
            if (range === null || (key >= range.start && key <= range.end)) {
                var val = series[key];
                if (typeof val === 'number') total += val;
            }
        }
        return total;
    }

    function sumActivitiesDaily(series, range) {
        if (!series) return 0;
        var total = 0;
        for (var key in series) {
            if (range === null || (key >= range.start && key <= range.end)) {
                var counts = series[key];
                for (var t in counts) total += (counts[t] || 0);
            }
        }
        return total;
    }

    function getActivityBreakdown(series, range) {
        var result = {calls: 0, emails: 0, meetings: 0, tasks: 0, notes: 0};
        if (!series) return result;
        for (var key in series) {
            if (range === null || (key >= range.start && key <= range.end)) {
                var counts = series[key];
                for (var t in counts) {
                    if (result.hasOwnProperty(t)) result[t] += (counts[t] || 0);
                }
            }
        }
        return result;
    }

    function filterDailyToMonthly(series, range) {
        if (!series) return {};
        var months = {};
        for (var key in series) {
            if (range === null || (key >= range.start && key <= range.end)) {
                var mk = key.substring(0, 7);
                months[mk] = (months[mk] || 0) + (typeof series[key] === 'number' ? series[key] : 0);
            }
        }
        return months;
    }

    function fmtNum(v) {
        if (v === null || v === undefined) return '0';
        if (v >= 1000000) return (v / 1000000).toFixed(1) + 'M';
        if (v >= 1000) return (v / 1000).toFixed(1) + 'K';
        return v.toLocaleString('en-GB', {maximumFractionDigits: 0});
    }

    function fmtCurrency(v) {
        if (v === null || v === undefined) return '\u00a30';
        if (v >= 1000000) return '\u00a3' + (v / 1000000).toFixed(1) + 'M';
        if (v >= 1000) return '\u00a3' + (v / 1000).toFixed(1) + 'K';
        return '\u00a3' + v.toLocaleString('en-GB', {maximumFractionDigits: 0});
    }

    function yoyBadge(metricKey) {
        var yoy = YOY[metricKey];
        if (!yoy || yoy.change_pct === null || yoy.change_pct === undefined) return '';
        var pct = yoy.change_pct;
        var cls = pct > 0 ? 'up' : pct < 0 ? 'down' : 'neutral';
        var arrow = pct > 0 ? '\u2191' : pct < 0 ? '\u2193' : '\u2192';
        var sign = pct > 0 ? '+' : '';
        return '<span class="yoy-badge ' + cls + '">' + arrow + ' ' + sign + pct.toFixed(1) + '% YoY</span>';
    }


    // ------------------------------------------------------------------
    // Toast notification
    // ------------------------------------------------------------------
    function showToast(msg, type) {
        var t = document.createElement('div');
        t.className = 'toast-msg ' + (type || 'info');
        t.textContent = msg;
        t.style.cssText = 'position:fixed;top:20px;right:20px;z-index:99999;padding:12px 20px;border-radius:8px;'
            + 'font-size:13px;font-weight:600;color:#fff;box-shadow:0 4px 12px rgba(0,0,0,0.15);'
            + 'animation:chatSlideIn 0.25s ease;'
            + 'background:' + (type === 'error' ? '#ef4444' : type === 'success' ? '#10b981' : '#3CB4AD');
        document.body.appendChild(t);
        setTimeout(function () { t.remove(); }, 3500);
    }

    // ------------------------------------------------------------------
    // Branded print window (shared by chat widget + anna page)
    // ------------------------------------------------------------------
    function openPrintWindow(title, htmlContent) {
        var now = new Date();
        var dateStr = now.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
        var timeStr = now.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
        var w = window.open('', '_blank');
        if (!w) { showToast('Please allow pop-ups to export reports', 'error'); return; }
        var html = '<!DOCTYPE html><html><head>'
            + '<meta charset="UTF-8"><title>' + title + '</title>'
            + '<link href="https://fonts.googleapis.com/css2?family=Assistant:wght@400;600;700;800&display=swap" rel="stylesheet">'
            + '<style>'
            + 'body{font-family:"Assistant",sans-serif;color:#121212;margin:0;padding:40px;line-height:1.6}'
            + '.rpt-header{border-bottom:3px solid #3CB4AD;padding-bottom:16px;margin-bottom:24px}'
            + '.rpt-brand{display:flex;align-items:center;gap:10px;margin-bottom:8px}'
            + '.rpt-dot{width:28px;height:28px;border-radius:50%;background:#3CB4AD;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:800;color:#fff}'
            + '.rpt-name{font-size:18px;font-weight:800;color:#242833}'
            + '.rpt-title{font-size:22px;font-weight:700;color:#242833;margin:8px 0 4px}'
            + '.rpt-meta{font-size:12px;color:#6b7280}'
            + '.rpt-body{font-size:14px}.rpt-body strong{font-weight:700}'
            + '.rpt-body ul,.rpt-body ol{margin:8px 0;padding-left:24px}.rpt-body li{margin-bottom:4px}'
            + '.rpt-body code{background:#f3f4f6;padding:2px 5px;border-radius:3px;font-size:13px}'
            + '.rpt-footer{margin-top:40px;padding-top:16px;border-top:1px solid #e2e5ea;font-size:11px;color:#6b7280;text-align:center}'
            + '@media print{body{padding:20px}.rpt-header{border-bottom-width:2px}}'
            + '</style></head><body>'
            + '<div class="rpt-header"><div class="rpt-brand"><div class="rpt-dot">e</div><span class="rpt-name">eComplete</span></div>'
            + '<div class="rpt-title">' + title + '</div>'
            + '<div class="rpt-meta">Generated by eComplete AI &middot; ' + dateStr + ' at ' + timeStr + '</div></div>'
            + '<div class="rpt-body">' + htmlContent + '</div>'
            + '<div class="rpt-footer">eComplete &mdash; Sales &amp; M&amp;A Intelligence Dashboard &middot; Confidential</div>'
            + '<scr' + 'ipt>window.onload=function(){ window.print(); }</scr' + 'ipt>'
            + '</body></html>';
        w.document.write(html);
        w.document.close();
    }

    // ------------------------------------------------------------------
    // Text formatting — shared by chat-widget.js + anna-page.js
    // ------------------------------------------------------------------
    function escHtml(s) {
        if (!s) return '';
        return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }

    function md(text) {
        if (!text) return '';
        var s = text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
        s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
        s = s.replace(/^[\-\*] (.+)$/gm, '<li>$1</li>');
        s = s.replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>');
        s = s.replace(/<\/ul>\s*<ul>/g, '');
        s = s.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');
        s = s.replace(/\n/g, '<br>');
        s = s.replace(/(<br>){3,}/g, '<br><br>');
        return s;
    }

    // Expose to global scope
    window.escHtml = escHtml;
    window.md = md;
    window.getDateRange = getDateRange;
    window.formatDate = formatDate;
    window.sumDaily = sumDaily;
    window.sumActivitiesDaily = sumActivitiesDaily;
    window.getActivityBreakdown = getActivityBreakdown;
    window.filterDailyToMonthly = filterDailyToMonthly;
    window.fmtNum = fmtNum;
    window.fmtCurrency = fmtCurrency;
    window.yoyBadge = yoyBadge;
    window.showToast = showToast;
    window.openPrintWindow = openPrintWindow;
})();
