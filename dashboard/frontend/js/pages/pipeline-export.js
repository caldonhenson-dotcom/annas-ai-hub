/* ============================================================
   Pipeline Export — CSV & PDF marketing reports
   Depends on render-pipeline.js (shared data), jsPDF + autotable
   ============================================================ */
(function () {
    'use strict';

    var MONTH_SHORT = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    var STAGE_ORDER = [
        'Qualified Lead', 'Engaged', 'First Meeting Booked',
        'Second Meeting Booked', 'Proposal Shared',
        'Decision Maker Bought-In', 'Contract Sent',
        'Closed Won', 'Closed Lost', 'Disqualified', 'Re-engage'
    ];

    function fmtK(v) {
        if (v >= 1000000) return '\u00a3' + (v / 1000000).toFixed(2) + 'M';
        if (v >= 1000) return '\u00a3' + (v / 1000).toFixed(1) + 'K';
        return '\u00a3' + Number(v || 0).toLocaleString('en-GB');
    }
    function fmtCurrency(v) {
        return '\u00a3' + Number(v || 0).toLocaleString('en-GB', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
    }
    function fmtDate(iso) {
        if (!iso) return '';
        var d = new Date(iso);
        return d.getDate() + ' ' + MONTH_SHORT[d.getMonth()] + ' ' + d.getFullYear();
    }
    function esc(s) { var d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }

    function getPeriodLabel(period) {
        if (period === '30d') return 'Past 30 Days';
        if (period === 'mtd') return 'This Month';
        if (period === 'ytd') return 'Year to Date';
        return 'All Time';
    }

    function today() {
        var d = new Date();
        return d.getDate() + ' ' + MONTH_SHORT[d.getMonth()] + ' ' + d.getFullYear();
    }

    // ================================================================
    // CSV Export
    // ================================================================
    function exportCSV(deals) {
        var headers = ['Deal Name','Deal Stage','Create Date','Close Date','Product','eComplete Source','Amount','Weighted Amount','Deal Owner','Closed Lost Reason','Closed Won Reason'];
        var rows = [headers.join(',')];
        deals.forEach(function (d) {
            rows.push([
                csvCell(d.name), csvCell(d.stage), csvCell(d.created), csvCell(d.closed),
                csvCell(d.product), csvCell(d.source), d.amount || 0, d.weighted || 0,
                csvCell(d.owner), csvCell(d.lostReason), csvCell(d.wonReason)
            ].join(','));
        });
        downloadFile(rows.join('\n'), 'deals-export-' + new Date().toISOString().slice(0,10) + '.csv', 'text/csv');
    }

    function csvCell(v) {
        if (!v) return '';
        v = String(v);
        if (v.indexOf(',') !== -1 || v.indexOf('"') !== -1 || v.indexOf('\n') !== -1) {
            return '"' + v.replace(/"/g, '""') + '"';
        }
        return v;
    }

    function downloadFile(content, filename, type) {
        var blob = new Blob([content], { type: type + ';charset=utf-8' });
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url; a.download = filename; a.style.display = 'none';
        document.body.appendChild(a);
        a.click();
        setTimeout(function () { document.body.removeChild(a); URL.revokeObjectURL(url); }, 100);
    }

    // ================================================================
    // PDF Library Loader — retry on demand if CDN failed at page load
    // ================================================================
    function loadScript(src) {
        return new Promise(function (resolve, reject) {
            var s = document.createElement('script');
            s.src = src;
            s.onload = resolve;
            s.onerror = reject;
            document.head.appendChild(s);
        });
    }

    function ensurePDFLibs() {
        if (window.jspdf && window.jspdf.jsPDF) return Promise.resolve();
        return loadScript('https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.2/jspdf.umd.min.js')
            .then(function () {
                return loadScript('https://cdnjs.cloudflare.com/ajax/libs/jspdf-autotable/3.8.4/jspdf.plugin.autotable.min.js');
            });
    }

    // ================================================================
    // PDF Export — Marketing Report
    // ================================================================
    function exportPDF(filtered, allDeals, period) {
        ensurePDFLibs().then(function () {
            if (!window.jspdf || !window.jspdf.jsPDF) {
                if (window.Toast) Toast.error('PDF library failed to load — check your network or ad blocker.');
                else alert('PDF library failed to load. Check your network connection or ad blocker.');
                return;
            }
            _generatePDF(filtered, allDeals, period);
        }).catch(function () {
            if (window.Toast) Toast.error('Could not download PDF library — check your connection.');
            else alert('Could not download PDF library. Check your internet connection.');
        });
    }

    function _generatePDF(filtered, allDeals, period) {
        var jsPDF = window.jspdf.jsPDF;
        var doc = new jsPDF('p', 'mm', 'a4');
        var pageW = doc.internal.pageSize.getWidth();
        var margin = 14;
        var contentW = pageW - margin * 2;
        var y = margin;

        // ── Colours ──
        var accent = [60, 180, 173];
        var dark = [26, 29, 42];
        var muted = [100, 110, 130];
        var success = [34, 197, 94];
        var danger = [239, 68, 68];

        // ── Page Header ──
        function pageHeader() {
            doc.setFillColor.apply(doc, dark);
            doc.rect(0, 0, pageW, 28, 'F');
            doc.setTextColor(255, 255, 255);
            doc.setFontSize(16);
            doc.setFont('helvetica', 'bold');
            doc.text('eComplete Deal Pipeline Report', margin, 13);
            doc.setFontSize(9);
            doc.setFont('helvetica', 'normal');
            doc.text(getPeriodLabel(period) + '  |  Generated ' + today(), margin, 20);
            doc.setTextColor.apply(doc, accent);
            doc.text('eComplete Intelligence', pageW - margin, 13, { align: 'right' });
            doc.setTextColor(0, 0, 0);
            y = 34;
        }

        function checkPageBreak(needed) {
            if (y + needed > doc.internal.pageSize.getHeight() - 15) {
                doc.addPage();
                pageHeader();
            }
        }

        function sectionTitle(title) {
            checkPageBreak(14);
            doc.setFontSize(12);
            doc.setFont('helvetica', 'bold');
            doc.setTextColor.apply(doc, dark);
            doc.text(title, margin, y);
            y += 2;
            doc.setDrawColor.apply(doc, accent);
            doc.setLineWidth(0.5);
            doc.line(margin, y, margin + contentW, y);
            y += 6;
        }

        function kpiBlock(label, value, x, w) {
            doc.setFillColor(245, 247, 250);
            doc.roundedRect(x, y, w, 18, 2, 2, 'F');
            doc.setFontSize(8);
            doc.setFont('helvetica', 'normal');
            doc.setTextColor.apply(doc, muted);
            doc.text(label.toUpperCase(), x + w / 2, y + 5, { align: 'center' });
            doc.setFontSize(14);
            doc.setFont('helvetica', 'bold');
            doc.setTextColor.apply(doc, dark);
            doc.text(value, x + w / 2, y + 14, { align: 'center' });
        }

        // ── Start building PDF ──
        pageHeader();

        // ── Executive Summary ──
        sectionTitle('Executive Summary');
        var open = filtered.filter(function(d) { return !d.isWon && !d.isLost; });
        var won = filtered.filter(function(d) { return d.isWon; });
        var lost = filtered.filter(function(d) { return d.isLost; });
        var totalVal = filtered.reduce(function(s, d) { return s + d.amount; }, 0);
        var openVal = open.reduce(function(s, d) { return s + d.amount; }, 0);
        var wonVal = won.reduce(function(s, d) { return s + d.amount; }, 0);
        var lostVal = lost.reduce(function(s, d) { return s + d.amount; }, 0);
        var winRate = (won.length + lost.length) > 0 ? (won.length / (won.length + lost.length) * 100).toFixed(1) : '0';
        var avgDeal = filtered.length > 0 ? totalVal / filtered.length : 0;

        var kpiW = (contentW - 8) / 3;
        kpiBlock('Total Pipeline', fmtK(totalVal), margin, kpiW);
        kpiBlock('Open Pipeline', fmtK(openVal), margin + kpiW + 4, kpiW);
        kpiBlock('Closed Won', fmtK(wonVal), margin + (kpiW + 4) * 2, kpiW);
        y += 22;

        kpiBlock('Closed Lost', fmtK(lostVal), margin, kpiW);
        kpiBlock('Win Rate', winRate + '%', margin + kpiW + 4, kpiW);
        kpiBlock('Avg Deal Size', fmtK(avgDeal), margin + (kpiW + 4) * 2, kpiW);
        y += 24;

        // ── Department Breakdown ──
        sectionTitle('Department Breakdown');
        var depts = {};
        filtered.forEach(function(d) {
            var prods = d.product ? d.product.split(';') : ['Unassigned'];
            prods.forEach(function(p) {
                p = p.trim() || 'Unassigned';
                if (!depts[p]) depts[p] = { count: 0, amount: 0, won: 0, lost: 0, open: 0, wonCount: 0, lostCount: 0 };
                depts[p].count++; depts[p].amount += d.amount;
                if (d.isWon) { depts[p].won += d.amount; depts[p].wonCount++; }
                else if (d.isLost) { depts[p].lost += d.amount; depts[p].lostCount++; }
                else depts[p].open += d.amount;
            });
        });

        var deptRows = Object.keys(depts).sort(function(a, b) { return depts[b].amount - depts[a].amount; }).map(function(k) {
            var d = depts[k];
            var closed = d.wonCount + d.lostCount;
            return [k, String(d.count), fmtCurrency(d.amount), fmtCurrency(d.open), fmtCurrency(d.won), fmtCurrency(d.lost), closed > 0 ? (d.wonCount / closed * 100).toFixed(0) + '%' : '-'];
        });

        if (deptRows.length) {
            doc.autoTable({
                startY: y,
                head: [['Department', 'Deals', 'Total Value', 'Open', 'Won', 'Lost', 'Win %']],
                body: deptRows,
                margin: { left: margin, right: margin },
                styles: { fontSize: 8, cellPadding: 2 },
                headStyles: { fillColor: accent, textColor: [255, 255, 255], fontStyle: 'bold', fontSize: 8 },
                alternateRowStyles: { fillColor: [248, 249, 252] },
                columnStyles: {
                    1: { halign: 'center' }, 2: { halign: 'right', fontStyle: 'bold' },
                    3: { halign: 'right' }, 4: { halign: 'right' },
                    5: { halign: 'right' }, 6: { halign: 'center', fontStyle: 'bold' }
                }
            });
            y = doc.lastAutoTable.finalY + 8;
        }

        // ── Deal Stage Funnel ──
        sectionTitle('Deal Stage Funnel');
        var stageCounts = {};
        filtered.forEach(function(d) { stageCounts[d.stage] = (stageCounts[d.stage] || 0) + 1; });
        var funnelRows = STAGE_ORDER.filter(function(s) { return stageCounts[s]; }).map(function(s) {
            var c = stageCounts[s];
            return [s, String(c), fmtCurrency(filtered.filter(function(d) { return d.stage === s; }).reduce(function(sum, d) { return sum + d.amount; }, 0)), (c / (filtered.length || 1) * 100).toFixed(1) + '%'];
        });

        if (funnelRows.length) {
            doc.autoTable({
                startY: y,
                head: [['Stage', 'Count', 'Value', '% Share']],
                body: funnelRows,
                margin: { left: margin, right: margin },
                styles: { fontSize: 8, cellPadding: 2 },
                headStyles: { fillColor: accent, textColor: [255, 255, 255], fontStyle: 'bold', fontSize: 8 },
                alternateRowStyles: { fillColor: [248, 249, 252] },
                columnStyles: { 1: { halign: 'center' }, 2: { halign: 'right', fontStyle: 'bold' }, 3: { halign: 'center' } }
            });
            y = doc.lastAutoTable.finalY + 8;
        }

        // ── Source Analysis ──
        sectionTitle('Lead Source Analysis');
        var sources = {};
        filtered.forEach(function(d) {
            var k = d.source || 'Unknown';
            if (!sources[k]) sources[k] = { count: 0, amount: 0, won: 0, wonCount: 0 };
            sources[k].count++; sources[k].amount += d.amount;
            if (d.isWon) { sources[k].won += d.amount; sources[k].wonCount++; }
        });
        var srcRows = Object.keys(sources).sort(function(a, b) { return sources[b].amount - sources[a].amount; }).map(function(k) {
            var s = sources[k];
            return [k, String(s.count), fmtCurrency(s.amount), String(s.wonCount), fmtCurrency(s.won)];
        });

        if (srcRows.length) {
            doc.autoTable({
                startY: y,
                head: [['Source', 'Deals', 'Pipeline Value', 'Won Count', 'Won Value']],
                body: srcRows,
                margin: { left: margin, right: margin },
                styles: { fontSize: 8, cellPadding: 2 },
                headStyles: { fillColor: accent, textColor: [255, 255, 255], fontStyle: 'bold', fontSize: 8 },
                alternateRowStyles: { fillColor: [248, 249, 252] },
                columnStyles: { 1: { halign: 'center' }, 2: { halign: 'right', fontStyle: 'bold' }, 3: { halign: 'center' }, 4: { halign: 'right' } }
            });
            y = doc.lastAutoTable.finalY + 8;
        }

        // ── Sales Rep Performance ──
        sectionTitle('Sales Rep Performance');
        var reps = {};
        filtered.forEach(function(d) {
            var k = d.owner || 'Unassigned';
            if (!reps[k]) reps[k] = { count: 0, amount: 0, won: 0, lost: 0, wonCount: 0, lostCount: 0 };
            reps[k].count++; reps[k].amount += d.amount;
            if (d.isWon) { reps[k].won += d.amount; reps[k].wonCount++; }
            if (d.isLost) { reps[k].lost += d.amount; reps[k].lostCount++; }
        });
        var repRows = Object.keys(reps).sort(function(a, b) { return reps[b].amount - reps[a].amount; }).map(function(k) {
            var r = reps[k];
            var closed = r.wonCount + r.lostCount;
            return [k, String(r.count), fmtCurrency(r.amount), fmtCurrency(r.won), fmtCurrency(r.lost), closed > 0 ? (r.wonCount / closed * 100).toFixed(0) + '%' : '-'];
        });

        if (repRows.length) {
            doc.autoTable({
                startY: y,
                head: [['Rep', 'Deals', 'Total Value', 'Won', 'Lost', 'Win %']],
                body: repRows,
                margin: { left: margin, right: margin },
                styles: { fontSize: 8, cellPadding: 2 },
                headStyles: { fillColor: accent, textColor: [255, 255, 255], fontStyle: 'bold', fontSize: 8 },
                alternateRowStyles: { fillColor: [248, 249, 252] },
                columnStyles: {
                    1: { halign: 'center' }, 2: { halign: 'right', fontStyle: 'bold' },
                    3: { halign: 'right' }, 4: { halign: 'right' }, 5: { halign: 'center', fontStyle: 'bold' }
                }
            });
            y = doc.lastAutoTable.finalY + 8;
        }

        // ── Full Deal Table ──
        sectionTitle('Deal Detail');
        var dealTableRows = filtered.map(function(d) {
            return [d.name || '', d.stage || '', fmtDate(d.created), d.product || '', d.source || '', fmtCurrency(d.amount), d.owner || ''];
        });

        if (dealTableRows.length) {
            doc.autoTable({
                startY: y,
                head: [['Deal Name', 'Stage', 'Created', 'Product', 'Source', 'Amount', 'Owner']],
                body: dealTableRows,
                margin: { left: margin, right: margin },
                styles: { fontSize: 7, cellPadding: 1.5, overflow: 'ellipsize' },
                headStyles: { fillColor: accent, textColor: [255, 255, 255], fontStyle: 'bold', fontSize: 7 },
                alternateRowStyles: { fillColor: [248, 249, 252] },
                columnStyles: { 0: { cellWidth: 40 }, 5: { halign: 'right', fontStyle: 'bold' } }
            });
            y = doc.lastAutoTable.finalY + 8;
        }

        // ── Footer on all pages ──
        var pageCount = doc.internal.getNumberOfPages();
        for (var i = 1; i <= pageCount; i++) {
            doc.setPage(i);
            doc.setFontSize(7);
            doc.setTextColor.apply(doc, muted);
            doc.text('eComplete Intelligence  |  Confidential', margin, doc.internal.pageSize.getHeight() - 6);
            doc.text('Page ' + i + ' of ' + pageCount, pageW - margin, doc.internal.pageSize.getHeight() - 6, { align: 'right' });
        }

        doc.save('eComplete-Pipeline-Report-' + new Date().toISOString().slice(0, 10) + '.pdf');
    }

    // ================================================================
    // Department CSV Export
    // ================================================================
    function exportDeptCSV(filtered) {
        var depts = {};
        filtered.forEach(function(d) {
            var prods = d.product ? d.product.split(';') : ['Unassigned'];
            prods.forEach(function(p) {
                p = p.trim() || 'Unassigned';
                if (!depts[p]) depts[p] = { count: 0, amount: 0, won: 0, lost: 0, open: 0, wonCount: 0, lostCount: 0 };
                depts[p].count++; depts[p].amount += d.amount;
                if (d.isWon) { depts[p].won += d.amount; depts[p].wonCount++; }
                else if (d.isLost) { depts[p].lost += d.amount; depts[p].lostCount++; }
                else depts[p].open += d.amount;
            });
        });

        var headers = ['Department','Deals','Total Value','Open Value','Won Value','Lost Value','Won Count','Lost Count','Win Rate'];
        var rows = [headers.join(',')];
        Object.keys(depts).sort(function(a, b) { return depts[b].amount - depts[a].amount; }).forEach(function(k) {
            var d = depts[k];
            var closed = d.wonCount + d.lostCount;
            rows.push([csvCell(k), d.count, d.amount.toFixed(2), d.open.toFixed(2), d.won.toFixed(2), d.lost.toFixed(2), d.wonCount, d.lostCount, closed > 0 ? (d.wonCount / closed * 100).toFixed(1) + '%' : '0%'].join(','));
        });
        downloadFile(rows.join('\n'), 'department-breakdown-' + new Date().toISOString().slice(0, 10) + '.csv', 'text/csv');
    }

    // ================================================================
    // Export Preview (for UI)
    // ================================================================
    function buildPreview(filtered, period) {
        var open = filtered.filter(function(d) { return !d.isWon && !d.isLost; });
        var won = filtered.filter(function(d) { return d.isWon; });
        var lost = filtered.filter(function(d) { return d.isLost; });
        var totalVal = filtered.reduce(function(s, d) { return s + d.amount; }, 0);
        var openVal = open.reduce(function(s, d) { return s + d.amount; }, 0);
        var wonVal = won.reduce(function(s, d) { return s + d.amount; }, 0);
        var lostVal = lost.reduce(function(s, d) { return s + d.amount; }, 0);

        var html = '<div class="pl-export-preview-title">Report Preview — ' + getPeriodLabel(period) + '</div>';

        // Summary
        html += '<table class="pl-breakdown-table"><thead><tr><th>Metric</th><th class="num">Value</th></tr></thead><tbody>'
            + '<tr><td style="font-weight:600">Total Deals</td><td class="num">' + filtered.length + '</td></tr>'
            + '<tr><td style="font-weight:600">Total Pipeline Value</td><td class="num" style="font-weight:700">' + fmtK(totalVal) + '</td></tr>'
            + '<tr><td style="font-weight:600">Open Pipeline</td><td class="num">' + fmtK(openVal) + ' (' + open.length + ' deals)</td></tr>'
            + '<tr><td style="font-weight:600;color:var(--success)">Closed Won</td><td class="num" style="color:var(--success)">' + fmtK(wonVal) + ' (' + won.length + ')</td></tr>'
            + '<tr><td style="font-weight:600;color:var(--danger)">Closed Lost</td><td class="num" style="color:var(--danger)">' + fmtK(lostVal) + ' (' + lost.length + ')</td></tr>'
            + '</tbody></table>';

        // Department mini summary
        var depts = {};
        filtered.forEach(function(d) {
            var prods = d.product ? d.product.split(';') : ['Unassigned'];
            prods.forEach(function(p) {
                p = p.trim() || 'Unassigned';
                if (!depts[p]) depts[p] = { count: 0, amount: 0 };
                depts[p].count++; depts[p].amount += d.amount;
            });
        });
        var deptKeys = Object.keys(depts).sort(function(a, b) { return depts[b].amount - depts[a].amount; });
        if (deptKeys.length) {
            html += '<div style="margin-top:12px;font-size:12px;font-weight:700;color:var(--text)">By Department</div>'
                + '<table class="pl-breakdown-table" style="margin-top:4px"><thead><tr><th>Dept</th><th class="num">Deals</th><th class="num">Value</th></tr></thead><tbody>';
            deptKeys.forEach(function(k) {
                html += '<tr><td style="font-weight:600">' + esc(k) + '</td><td class="num">' + depts[k].count + '</td><td class="num" style="font-weight:600">' + fmtK(depts[k].amount) + '</td></tr>';
            });
            html += '</tbody></table>';
        }

        return html;
    }

    // ================================================================
    // Master Renderer
    // ================================================================
    window.renderPipelineExport = function (filtered, allDeals, period) {
        var el = document.getElementById('pl-export-container');
        if (!el) return;

        var html = '<div class="pl-export-options">'
            + '<button class="pl-export-btn" id="pl-btn-csv">'
            + '<span class="pl-export-icon">&#128196;</span>'
            + '<div><strong>Export CSV</strong><div class="pl-export-btn-desc">Deals table — all filtered data</div></div></button>'

            + '<button class="pl-export-btn" id="pl-btn-dept-csv">'
            + '<span class="pl-export-icon">&#128202;</span>'
            + '<div><strong>Department CSV</strong><div class="pl-export-btn-desc">Rolled-up departmental breakdown</div></div></button>'

            + '<button class="pl-export-btn" id="pl-btn-pdf">'
            + '<span class="pl-export-icon">&#128220;</span>'
            + '<div><strong>Full PDF Report</strong><div class="pl-export-btn-desc">Marketing report — summary, departments, sources, reps, deals</div></div></button>'
            + '</div>';

        html += '<div class="pl-export-preview">' + buildPreview(filtered, period) + '</div>';

        el.innerHTML = html;

        // Wire export buttons
        var btnCSV = document.getElementById('pl-btn-csv');
        var btnDeptCSV = document.getElementById('pl-btn-dept-csv');
        var btnPDF = document.getElementById('pl-btn-pdf');

        if (btnCSV) btnCSV.addEventListener('click', function () { exportCSV(filtered); });
        if (btnDeptCSV) btnDeptCSV.addEventListener('click', function () { exportDeptCSV(filtered); });
        if (btnPDF) btnPDF.addEventListener('click', function () { exportPDF(filtered, allDeals, period); });
    };
})();
