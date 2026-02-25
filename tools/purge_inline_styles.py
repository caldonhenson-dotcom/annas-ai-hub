#!/usr/bin/env python3
"""
Bulk-replace inline style="" attributes with utility CSS classes.

Reads each page fragment in dashboard/frontend/pages/ and replaces
the top 30 most-repeated inline style patterns with class names
from utilities.css. Handles both style-only and style+class merges.

Run once from the repo root:
    python tools/purge_inline_styles.py
"""
import re, os, glob

PAGES_DIR = os.path.join(os.path.dirname(__file__), '..', 'dashboard', 'frontend', 'pages')
INDEX_PATH = os.path.join(os.path.dirname(__file__), '..', 'dashboard', 'frontend', 'index.html')

# ── Map: exact inline style → utility class(es) ──
# Order matters: longer/more-specific patterns first to avoid partial matches
STYLE_TO_CLASS = [
    # Compound cell patterns (inbound-queue, monday boards)
    ('padding:6px;font-weight:500;color:#121212',          'cell-pad-value'),
    ('padding:6px;color:#6b7280;text-transform:capitalize', 'cell-pad-cap'),
    ('padding:6px;color:#334FB4;font-size:11px',            'cell-pad-accent2'),
    ('padding:6px;color:#6b7280',                           'cell-pad-muted'),
    ('padding:6px',                                          'cell-pad'),

    # Text with margin-left
    ('font-size:10px;color:#6b7280;margin-left:auto',       'text-muted-xs-ml'),
    ('font-size:10px;color:#6b7280;margin-left:8px',        'text-muted-xs-ml8'),
    ('font-size:10px;color:#6b7280;margin-left:6px',        'text-muted-xs-ml6'),

    # Text compound styles
    ('font-size:20px;font-weight:800;color:#121212',        'text-hero'),
    ('font-size:12px;color:#121212;font-weight:500',        'text-value'),
    ('font-size:12px;color:#121212;margin-top:2px',         'text-value-sm'),
    ('font-size:11px;font-weight:600;color:#F44336',        'text-error-sm'),
    ('font-size:11px;color:#6b7280;font-style:italic',      'text-italic-muted'),
    ('font-weight:500;color:#121212',                        'text-primary'),
    ('font-weight:600;color:#121212',                        'text-primary'),
    ('font-size:11px;color:#6b7280',                         'text-muted-sm'),
    ('font-size:10px;color:#6b7280',                         'text-muted-xs'),
    ('font-size:12px;color:#6b7280',                         'text-label-sm'),
    ('color:#6b7280;text-decoration:line-through',           'text-strikethrough'),
    ('color:#121212;',                                       'text-dark'),
    ('color:#121212',                                        'text-dark'),
    ('font-size:12px',                                       'text-12'),

    # Board grid
    ('grid-template-columns:2fr 100px 100px',               'grid-board-3col'),

    # Progress bars
    ('width:100%;background:#00CA72',                        'bar-full-green'),

    # Status pills (inline)
    ('background:#00CA7222;color:#00CA72;min-width:auto;padding:2px 6px;margin:1px 2px;font-size:10px', 'pill-done-sm'),
    ('display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;background:#FFCB0033;color:#FFCB00', 'pill-working-sm'),

    # Borders & spacing
    ('padding:4px 0;border-bottom:1px solid #e2e5ea',       'row-pad-sep'),
    ('border-bottom:1px solid #e2e5ea',                      'border-bottom-sep'),
    ('margin-top:8px',                                       'mt-2'),

    # Interactive
    ('cursor:pointer;user-select:none',                      'clickable'),
    ('opacity:0.4;font-size:10px',                           'expand-arrow'),

    # Display
    ('display:none;',                                        'hidden'),
    ('display:none',                                         'hidden'),
]

def normalise(s):
    """Strip whitespace around colons and semicolons for fuzzy matching."""
    s = re.sub(r'\s*:\s*', ':', s)
    s = re.sub(r'\s*;\s*', ';', s)
    return s.strip().rstrip(';')

def build_pattern(style_str):
    """Build regex that matches style="..." with optional surrounding whitespace."""
    # Allow whitespace around colons/semicolons and optional trailing semicolon
    escaped = re.escape(style_str)
    # Make whitespace around : and ; flexible
    escaped = escaped.replace(r'\:', r'\s*:\s*')
    escaped = escaped.replace(r'\;', r'\s*;\s*')
    return escaped

def process_file(filepath):
    """Replace inline styles with classes in a single file. Returns replacement count."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content
    total = 0

    for style_val, class_name in STYLE_TO_CLASS:
        pattern_str = build_pattern(style_val)

        # Case 1: Element has ONLY this style (no existing class)
        # style="pattern" → class="classname"
        regex1 = re.compile(
            r'style\s*=\s*"' + pattern_str + r';?\s*"',
            re.IGNORECASE
        )
        count1 = len(regex1.findall(content))
        if count1 > 0:
            # Check if tag already has a class attribute
            # Replace style with class, but need to merge if class exists
            def replace_style_only(m):
                return 'class="' + class_name + '"'

            # First handle tags that DON'T have an existing class attr
            # Match: <tag ... style="pattern" ... > where no class=" before or after
            content_new = regex1.sub(replace_style_only, content)

            # Now merge any tags with both class="old" and class="new"
            # Pattern: class="X" ... class="Y" or class="Y" ... class="X"
            merge_re = re.compile(
                r'class="([^"]*?)"\s+class="(' + re.escape(class_name) + r')"'
            )
            content_new = merge_re.sub(lambda m: 'class="' + m.group(1) + ' ' + m.group(2) + '"', content_new)

            # Also handle reverse order
            merge_re2 = re.compile(
                r'class="(' + re.escape(class_name) + r')"\s+class="([^"]*?)"'
            )
            content_new = merge_re2.sub(lambda m: 'class="' + m.group(2) + ' ' + m.group(1) + '"', content_new)

            total += count1
            content = content_new

    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

    return total

def main():
    total_all = 0
    pages_dir = os.path.normpath(PAGES_DIR)

    # Process page fragments
    files = sorted(glob.glob(os.path.join(pages_dir, '*.html')))
    print(f'Purging inline styles from {len(files)} page fragments...\n')

    for filepath in files:
        count = process_file(filepath)
        name = os.path.basename(filepath)
        if count > 0:
            print(f'  {name:30s} {count:5d} replacements')
        total_all += count

    # Process index.html
    idx = os.path.normpath(INDEX_PATH)
    if os.path.exists(idx):
        count = process_file(idx)
        if count > 0:
            print(f'  {"index.html":30s} {count:5d} replacements')
        total_all += count

    # Count remaining inline styles
    remaining = 0
    for filepath in files + [idx]:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                remaining += len(re.findall(r'style\s*=\s*"', f.read()))

    print(f'\n  Total replacements: {total_all}')
    print(f'  Remaining style= : {remaining}')
    print(f'  Reduction:         {total_all}/{total_all + remaining} = {total_all / max(1, total_all + remaining) * 100:.0f}%')

if __name__ == '__main__':
    main()
