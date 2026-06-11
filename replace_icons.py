#!/usr/bin/env python3
"""Replace inline SVG icons and emojis with Lucide icons in all templates."""

import re
import os

TEMPLATES_DIR = 'templates'

# Mapping of emoji → lucide icon name (with class)
EMOJI_MAP = {
    '💰': '<i data-lucide="credit-card" class="w-4 h-4 shrink-0"></i>',
    '📝': '<i data-lucide="book-open" class="w-4 h-4 shrink-0"></i>',
    '📄': '<i data-lucide="file-text" class="w-4 h-4 shrink-0"></i>',
    '📊': '<i data-lucide="bar-chart-2" class="w-4 h-4 shrink-0"></i>',
    '📋': '<i data-lucide="clipboard-list" class="w-4 h-4 shrink-0"></i>',
    '🏆': '<i data-lucide="trophy" class="w-4 h-4 shrink-0"></i>',
    '⚡': '<i data-lucide="zap" class="w-4 h-4 shrink-0"></i>',
    '👋': '',
    '✅': '<i data-lucide="check-circle" class="w-4 h-4 shrink-0"></i>',
    '⏳': '<i data-lucide="clock" class="w-4 h-4 shrink-0"></i>',
    '❌': '<i data-lucide="x-circle" class="w-4 h-4 shrink-0"></i>',
    '📥': '<i data-lucide="download" class="w-4 h-4 shrink-0"></i>',
    '⚠️': '<i data-lucide="alert-triangle" class="w-4 h-4 shrink-0"></i>',
    '🥇': '<i data-lucide="medal" class="w-4 h-4 shrink-0 text-amber-400"></i>',
    '🥈': '<i data-lucide="medal" class="w-4 h-4 shrink-0 text-gray-400"></i>',
    '🥉': '<i data-lucide="medal" class="w-4 h-4 shrink-0 text-amber-700"></i>',
    '👁': '<i data-lucide="eye" class="w-4 h-4 shrink-0"></i>',
    '✓': '<i data-lucide="check" class="w-4 h-4 shrink-0"></i>',
    '→': '',
}

# SVG to Lucide mapping: key = recognizable path fragment, value = lucide icon name
SVG_LUCIDE_MAP = [
    # Path fragments → icon names (will match unique SVGs)
    ('M3 12l2-2m0 0l7-7 7 7M5 10v10', 'layout-dashboard'),
    ('M19 21V5a2 2 0 00-2-2H7', 'school'),
    # Note: users icon has a complex path, match by condition
    ('M12 4.354a4 4 0 110 5.292M15 21H3', 'users'),
    ('M3 10h18M7 15h1m4 0h1m-7 4h12', 'credit-card'),
    ('M11 5H6a2 2 0 00-2 2v11', 'book-open'),
    ('M9 12h6m-6 4h6m2 5H7a2 2', 'file-text'),
    ('M10.325 4.317c.426-1.756 2.924-1.756 3.35 0', 'settings'),
    ('M17 16l4-4m0 0l-4-4m4 4H7', 'log-out'),
    ('M12 4v16m8-8H4', 'plus'),
    ('M6 18L18 6M6 6l12 12', 'x'),
    ('M4 6a2 2 0 012-2h2a2 2 0 012 2v2', 'layout-grid'),
    ('M3 10h18M3 6h18M3 14h18M3 18h18', 'list'),
    ('M4 6h16M4 10h16M4 14h16M4 18h16', 'menu'),
    ('M10 19l-7-7m0 0l7-7m-7 7h18', 'arrow-left'),
    ('M15 19l-7-7 7-7', 'chevron-left'),
    ('M9 5l7 7-7 7', 'chevron-right'),
    ('M4 16v1a3 3 0 003 3h10', 'upload'),
    ('M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6', 'upload'),
    ('M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0', 'info'),
    ('M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2', 'download'),
    ('M5 13l4 4L19 7', 'check'),
    ('M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z', 'search'),
    ('M12 15v2m0 0v2m0-2h2m-2 0H10', 'alert-circle'),
    ('M8 7V3m8 4V3m-9 8h10M5 21h14', 'calendar'),
    ('M12 8v4l3 3m6-3a9 9 0 11-18 0', 'clock'),
    ('M4 5a1 1 0 011-1h14a1 1 0 011 1v2', 'layers'),
    ('M7 21h10a2 2 0 002-2V9.414', 'file'),
    ('M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10', 'file'),  # clipboard
    ('M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14', 'user'),
    ('M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684', 'phone'),
    ('M12 15v2m-6 4h12a2 2 0 002-2v-6', 'shield'),
    ('M9 19v-6a2 2 0 00-2-2H5', 'bar-chart-3'),
    ('M8 12h.01M12 12h.01M16 12h.01', 'message-circle'),
]

def has_svg(line):
    return '<svg' in line and 'class=' in line

def process_template(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original = content
    
    # Replace emojis
    for emoji, replacement in EMOJI_MAP.items():
        content = content.replace(emoji, replacement)
    
    # Replace SVG inline blocks - this is tricky because SVGs span multiple lines
    # We'll use a regex approach to find <svg>...</svg> blocks
    
    # Pattern to match SVG blocks (including multiline)
    svg_pattern = re.compile(r'<svg[^>]*>.*?</svg>', re.DOTALL)
    
    def replace_svg(match):
        svg_block = match.group(0)
        for path_fragment, icon_name in SVG_LUCIDE_MAP:
            if path_fragment in svg_block:
                # Extract class to get size info
                size_class = 'w-4 h-4'
                class_match = re.search(r'class="([^"]*)"', svg_block)
                if class_match:
                    classes = class_match.group(1)
                    # Try to extract width/height
                    w_match = re.search(r'w-(\d+)', classes)
                    h_match = re.search(r'h-(\d+)', classes)
                    if w_match and h_match:
                        size_class = f'w-{w_match.group(1)} h-{h_match.group(1)}'
                    elif 'shrink-0' in classes:
                        size_class = 'w-4 h-4'  # default
                return f'<i data-lucide="{icon_name}" class="{size_class} shrink-0"></i>'
        # No match found, return the SVG unchanged
        return svg_block
    
    content = svg_pattern.sub(replace_svg, content)
    
    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

def main():
    modified = []
    for root, dirs, files in os.walk(TEMPLATES_DIR):
        for file in files:
            if file.endswith('.html'):
                filepath = os.path.join(root, file)
                if process_template(filepath):
                    modified.append(filepath)
    
    print("=== Fichiers modifiés ===")
    for f in modified:
        print(f"  ✓ {f}")

if __name__ == '__main__':
    main()