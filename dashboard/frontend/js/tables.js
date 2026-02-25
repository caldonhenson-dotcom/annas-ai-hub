/* ============================================================
   EnhancedTable — sort, search, pagination
   ============================================================ */
(function () {
    'use strict';

    // ------------------------------------------------------------------
    // Legacy sortTable (still used by existing onclick attributes)
    // ------------------------------------------------------------------
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

        // Update arrow indicators
        table.querySelectorAll('th .sort-arrow').forEach(function (el, i) {
            el.classList.toggle('active', i === colIdx);
            el.innerHTML = (i === colIdx) ? (asc ? '&#9650;' : '&#9660;') : '&#9650;';
        });
    };

    // ------------------------------------------------------------------
    // EnhancedTable class
    // ------------------------------------------------------------------
    function EnhancedTable(containerId, opts) {
        this.containerId = containerId;
        this.opts = Object.assign({
            searchable: true,
            paginated: true,
            pageSize: 10,
            sortable: true,
            stickyHeader: true
        }, opts || {});

        this.headers = [];
        this.allRows = [];
        this.filteredRows = [];
        this.sortCol = -1;
        this.sortAsc = true;
        this.currentPage = 1;
        this.searchTimer = null;
    }

    EnhancedTable.prototype.setData = function (headers, rows) {
        this.headers = headers;
        this.allRows = rows.slice();
        this.filteredRows = rows.slice();
        this.currentPage = 1;
        this.sortCol = -1;
        return this;
    };

    EnhancedTable.prototype.render = function () {
        var container = document.getElementById(this.containerId);
        if (!container) return this;
        var self = this;
        var html = '';

        // Search bar
        if (this.opts.searchable) {
            html += '<div class="table-controls">'
                + '<input type="text" class="table-search" placeholder="Search..." '
                + 'id="' + this.containerId + '-search">'
                + '<span class="table-row-count text-muted-sm" id="'
                + this.containerId + '-count">'
                + this.filteredRows.length + ' rows</span></div>';
        }

        // Table
        var tableId = this.containerId + '-tbl';
        html += '<div class="table-wrapper">'
            + '<table class="data-table" id="' + tableId + '">'
            + '<thead><tr>';

        this.headers.forEach(function (h, i) {
            var label = typeof h === 'string' ? h : (h.label || '');
            var sortAttr = self.opts.sortable
                ? ' data-col="' + i + '" style="cursor:pointer"' : '';
            html += '<th' + sortAttr + '>' + label
                + (self.opts.sortable
                    ? ' <span class="sort-arrow">&#9650;</span>' : '')
                + '</th>';
        });

        html += '</tr></thead><tbody>';
        html += this._renderRows();
        html += '</tbody></table></div>';

        // Pagination
        if (this.opts.paginated) {
            html += this._renderPagination();
        }

        container.innerHTML = html;
        this._bindEvents(container);
        return this;
    };

    EnhancedTable.prototype._renderRows = function () {
        var start = (this.currentPage - 1) * this.opts.pageSize;
        var end = this.opts.paginated
            ? start + this.opts.pageSize : this.filteredRows.length;
        var pageRows = this.filteredRows.slice(start, end);
        var html = '';

        if (pageRows.length === 0) {
            html += '<tr><td colspan="' + this.headers.length
                + '" style="text-align:center;padding:24px;color:var(--text-muted)">'
                + 'No matching rows</td></tr>';
            return html;
        }

        pageRows.forEach(function (row) {
            html += '<tr>';
            row.forEach(function (cell) {
                var val = (typeof cell === 'object' && cell.html)
                    ? cell.html : String(cell);
                html += '<td>' + val + '</td>';
            });
            html += '</tr>';
        });
        return html;
    };

    EnhancedTable.prototype._renderPagination = function () {
        var total = this.filteredRows.length;
        var pages = Math.ceil(total / this.opts.pageSize) || 1;
        var html = '<div class="table-pagination">';

        // Page size selector
        html += '<select class="table-page-size" id="'
            + this.containerId + '-pagesize">';
        var self = this;
        [10, 25, 50].forEach(function (s) {
            html += '<option value="' + s + '"'
                + (s === self.opts.pageSize ? ' selected' : '')
                + '>' + s + ' / page</option>';
        });
        html += '</select>';

        // Page buttons
        html += '<div class="table-page-btns">';
        for (var i = 1; i <= Math.min(pages, 7); i++) {
            html += '<button class="table-page-btn'
                + (i === this.currentPage ? ' active' : '')
                + '" data-page="' + i + '">' + i + '</button>';
        }
        if (pages > 7) {
            html += '<span class="text-muted-sm" style="padding:0 4px">...</span>';
            html += '<button class="table-page-btn" data-page="'
                + pages + '">' + pages + '</button>';
        }
        html += '</div>';
        html += '<span class="text-muted-sm">Page '
            + this.currentPage + ' of ' + pages + '</span>';
        html += '</div>';
        return html;
    };

    EnhancedTable.prototype._bindEvents = function (container) {
        var self = this;

        // Search
        var search = container.querySelector('.table-search');
        if (search) {
            search.addEventListener('input', function () {
                clearTimeout(self.searchTimer);
                self.searchTimer = setTimeout(function () {
                    self.search(search.value);
                }, 300);
            });
        }

        // Sort headers
        container.querySelectorAll('th[data-col]').forEach(function (th) {
            th.addEventListener('click', function () {
                self.sort(parseInt(th.dataset.col, 10));
            });
        });

        this._bindPagination(container);
    };

    EnhancedTable.prototype._bindPagination = function (container) {
        var self = this;
        container.querySelectorAll('.table-page-btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                self.currentPage = parseInt(btn.dataset.page, 10);
                self._updateTable(container);
            });
        });
        var sel = container.querySelector('.table-page-size');
        if (sel) {
            sel.addEventListener('change', function () {
                self.opts.pageSize = parseInt(sel.value, 10);
                self.currentPage = 1;
                self._updateTable(container);
            });
        }
    };

    EnhancedTable.prototype.sort = function (colIdx) {
        if (this.sortCol === colIdx) {
            this.sortAsc = !this.sortAsc;
        } else {
            this.sortCol = colIdx;
            this.sortAsc = true;
        }
        var asc = this.sortAsc;
        this.filteredRows.sort(function (a, b) {
            var aVal = typeof a[colIdx] === 'object'
                ? (a[colIdx].text || '') : String(a[colIdx]);
            var bVal = typeof b[colIdx] === 'object'
                ? (b[colIdx].text || '') : String(b[colIdx]);
            var aNum = parseFloat(aVal.replace(/[^0-9.\-]/g, ''));
            var bNum = parseFloat(bVal.replace(/[^0-9.\-]/g, ''));
            if (!isNaN(aNum) && !isNaN(bNum)) {
                return asc ? aNum - bNum : bNum - aNum;
            }
            return asc ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
        });
        this.currentPage = 1;
        var container = document.getElementById(this.containerId);
        if (container) this._updateTable(container);
    };

    EnhancedTable.prototype.search = function (query) {
        var q = (query || '').toLowerCase().trim();
        if (!q) {
            this.filteredRows = this.allRows.slice();
        } else {
            this.filteredRows = this.allRows.filter(function (row) {
                return row.some(function (cell) {
                    var text = typeof cell === 'object'
                        ? (cell.text || '') : String(cell);
                    return text.toLowerCase().indexOf(q) !== -1;
                });
            });
        }
        this.currentPage = 1;
        var container = document.getElementById(this.containerId);
        if (container) this._updateTable(container);
    };

    EnhancedTable.prototype._updateTable = function (container) {
        var tbody = container.querySelector('tbody');
        if (tbody) tbody.innerHTML = this._renderRows();

        // Update pagination
        var pag = container.querySelector('.table-pagination');
        if (pag) pag.outerHTML = this._renderPagination();
        this._bindPagination(container);

        // Update row count
        var ct = container.querySelector('.table-row-count');
        if (ct) ct.textContent = this.filteredRows.length + ' rows';

        // Update sort arrows
        var col = this.sortCol;
        var asc = this.sortAsc;
        container.querySelectorAll('th[data-col] .sort-arrow').forEach(function (el) {
            var c = parseInt(el.parentElement.dataset.col, 10);
            el.classList.toggle('active', c === col);
            el.innerHTML = (c === col) ? (asc ? '&#9650;' : '&#9660;') : '&#9650;';
        });
    };

    EnhancedTable.prototype.destroy = function () {
        var container = document.getElementById(this.containerId);
        if (container) container.innerHTML = '';
    };

    window.EnhancedTable = EnhancedTable;
})();
