/* ============================================================
   Tables — sortable column headers
   ============================================================ */
window.sortTable = function (tableId, colIdx) {
    var table = document.getElementById(tableId);
    if (!table) return;
    var tbody = table.querySelector('tbody');
    var rows = Array.from(tbody.querySelectorAll('tr'));
    var asc = table.getAttribute('data-sort-col') == colIdx
        && table.getAttribute('data-sort-dir') !== 'asc';

    rows.sort(function (a, b) {
        var aText = a.children[colIdx] ? a.children[colIdx].textContent.trim() : '';
        var bText = b.children[colIdx] ? b.children[colIdx].textContent.trim() : '';

        // Try numeric comparison (strip currency symbols, commas, %)
        var aNum = parseFloat(aText.replace(/[^0-9.\-]/g, ''));
        var bNum = parseFloat(bText.replace(/[^0-9.\-]/g, ''));

        if (!isNaN(aNum) && !isNaN(bNum)) {
            return asc ? aNum - bNum : bNum - aNum;
        }
        return asc ? aText.localeCompare(bText) : bText.localeCompare(aText);
    });

    rows.forEach(function (row) { tbody.appendChild(row); });
    table.setAttribute('data-sort-col', colIdx);
    table.setAttribute('data-sort-dir', asc ? 'asc' : 'desc');
};
