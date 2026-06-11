#!/usr/bin/env python3
"""Moderniser toutes les cards selon le nouveau design system."""

import re
import os

# Pattern pour les KPI/stats cards (Type 1)
# Avant: bg-white rounded-xl p-4 shadow-sm border border-gray-100
# Après: bg-white rounded-xl border border-gray-200 p-4 (ou p-3 mobile)
KPI_PATTERNS = [
    # Match exact: "bg-white rounded-xl p-4 shadow-sm border border-gray-100"  
    ('bg-white rounded-xl p-4 shadow-sm border border-gray-100', 
     'bg-white rounded-xl border border-gray-200 p-4'),
    ('bg-white rounded-xl p-3 sm:p-4 shadow-sm border border-gray-100',
     'bg-white rounded-xl border border-gray-200 p-3 sm:p-4'),
    ('bg-white rounded-xl p-5 shadow-sm border border-gray-100',
     'bg-white rounded-xl border border-gray-200 p-5'),
    ('bg-white rounded-xl shadow-sm border border-gray-100 p-5',
     'bg-white rounded-xl border border-gray-200 p-5'),
    # Class stats specific
    ('bg-white rounded-xl p-4 shadow-sm',
     'bg-white rounded-xl border border-gray-200 p-4'),
    # Payment stats
    ('bg-white rounded-xl border border-gray-100 shadow-sm',
     'bg-white rounded-xl border border-gray-200'),
    # Superadmin
    ('bg-white rounded-xl p-5 shadow-sm border border-gray-100',
     'bg-white rounded-xl border border-gray-200 p-5'),
    ('bg-white rounded-xl shadow-sm border border-gray-100 p-6',
     'bg-white rounded-xl border border-gray-200 p-6'),
    # Payment card
    ('bg-white rounded-xl border border-gray-100 shadow-sm p-4',
     'bg-white rounded-xl border border-gray-200 p-4'),
    # Payment list
    ('bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden',
     'bg-white rounded-xl border border-gray-200 overflow-hidden'),
    # Cards with hover shadow
    ('bg-white rounded-xl shadow-sm border border-gray-100 p-5 hover:shadow-md transition',
     'bg-white rounded-xl border border-gray-200 p-5 hover:shadow-sm transition-shadow duration-200'),
    # Class table body cards
    ('bg-white rounded-xl shadow-sm border border-gray-100 p-5 flex flex-col gap-3 hover:shadow-md transition',
     'bg-white rounded-xl border border-gray-200 p-5 flex flex-col gap-3 hover:shadow-sm transition-shadow duration-200'),
    # Student card
    ('bg-white rounded-xl shadow-sm border border-gray-100 p-5 flex flex-col gap-3 hover:shadow-md transition',
     'bg-white rounded-xl border border-gray-200 p-5 flex flex-col gap-3 hover:shadow-sm transition-shadow duration-200'),
    # Class progress card
    ('bg-white rounded-xl shadow-sm border border-gray-100 p-5 hover:shadow-md hover:border-brand-gold/30 transition group block',
     'bg-white rounded-xl border border-gray-200 p-5 hover:shadow-sm hover:border-brand-gold/30 transition-shadow duration-200 group block'),
    # Profile cards (rounded-2xl -> rounded-xl)
    ('bg-white rounded-2xl shadow-sm border border-gray-100 p-6',
     'bg-white rounded-xl border border-gray-200 p-6'),
    # KPI cards with animation
    ('bg-white rounded-xl shadow-sm border border-gray-100 p-5 hover:shadow-md transition-all duration-300 animate-fade-in',
     'bg-white rounded-xl border border-gray-200 p-5 hover:shadow-sm transition-shadow duration-200'),
    ('bg-white rounded-xl shadow-sm border border-gray-100 p-5 hover:shadow-md transition-all duration-300',
     'bg-white rounded-xl border border-gray-200 p-5 hover:shadow-sm transition-shadow duration-200'),
]

# Cards contenant "shadow-sm" -> remplacer par "border border-gray-200"
# Et "rounded-2xl" -> "rounded-xl" (sauf modales)
ADDITIONAL_PATTERNS = [
    # dashboard graph cards
    ('bg-white rounded-xl shadow-sm border border-gray-100 p-5',
     'bg-white rounded-xl border border-gray-200 p-5'),
    # activity_feed
    ('bg-white rounded-xl shadow-sm border border-gray-100 p-5',
     'bg-white rounded-xl border border-gray-200 p-5'),
    # class_health
    ('bg-white rounded-xl shadow-sm border border-gray-100 p-5 mb-8',
     'bg-white rounded-xl border border-gray-200 p-5 mb-8'),
    # rankings empty
    ('bg-white rounded-xl shadow-sm border border-gray-100 p-12 text-center',
     'bg-white rounded-xl border border-gray-200 p-12 text-center'),
    # notes_class empty
    ('bg-white rounded-xl shadow-sm border border-gray-100 p-12 text-center',
     'bg-white rounded-xl border border-gray-200 p-12 text-center'),
    # notes_table empty states
    ('bg-white rounded-xl shadow-sm border border-gray-100 p-8 text-center',
     'bg-white rounded-xl border border-gray-200 p-8 text-center'),
    # notes_dashboard empty
    ('bg-white rounded-xl p-8 text-center border border-dashed border-gray-200',
     'bg-white rounded-xl border border-dashed border-gray-200 p-8 text-center'),
    # superadmin table
    ('bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden',
     'bg-white rounded-xl border border-gray-200 overflow-hidden'),
    # student detail
    ('bg-white rounded-2xl shadow-sm border border-gray-100 p-6',
     'bg-white rounded-xl border border-gray-200 p-6'),
    # superadmin form cards
    ('bg-white rounded-xl shadow-sm border border-gray-100 p-6',
     'bg-white rounded-xl border border-gray-200 p-6'),
    # health_tab cards rounded-xl p-4
    ('p-4 shadow-sm border border-gray-100',
     'p-4 border border-gray-200'),
    # Student table body
    ('bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden',
     'bg-white rounded-xl border border-gray-200 overflow-hidden'),
    # Class_add_card
    ('bg-white rounded-xl border-2 border-dashed border-gray-200',
     'bg-white rounded-xl border-2 border-dashed border-gray-300'),
    # student_profile cards
    ('bg-white rounded-2xl shadow-sm border border-gray-100 p-6',
     'bg-white rounded-xl border border-gray-200 p-6'),
    # superadmin kpi cards
    ('bg-white rounded-xl p-5 shadow-sm border border-gray-100',
     'bg-white rounded-xl border border-gray-200 p-5'),
    # payment stats with border border-gray-100
    ('border border-gray-100', 'border border-gray-200'),
]

def update_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()
    
    original = content
    
    # Apply all patterns
    for old, new in ADDITIONAL_PATTERNS:
        content = content.replace(old, new)
    for old, new in KPI_PATTERNS:
        content = content.replace(old, new)
    
    # Final cleanup: ensure no remaining shadow-sm on cards (but keep on dropdowns/modals)
    # Replace "shadow-sm" when it's part of a card class
    # Only replace shadow-sm when preceded by "border border-gray-2"
    # to avoid affecting modals with shadow-xl/shadow-lg
    
    if content != original:
        with open(filepath, 'w') as f:
            f.write(content)
        return True
    return False

def main():
    files = [
        # Type 1 — KPI/Stats
        'templates/dashboard/partials/kpi_cards.html',
        'templates/notes/notes_dashboard.html',
        'templates/bulletins/partials/health_tab.html',
        'templates/payments/partials/payment_stats.html',
        'templates/schools/partials/class_stats.html',
        'templates/students/partials/student_stats.html',
        'templates/superadmin/dashboard.html',
        # Type 2 — Contenu principal
        'templates/dashboard/dashboard.html',
        'templates/dashboard/partials/activity_feed.html',
        'templates/dashboard/partials/class_health.html',
        'templates/bulletins/partials/rankings_tab.html',
        'templates/notes/notes_class.html',
        'templates/notes/partials/notes_table.html',
        'templates/notes/partials/class_progress_card.html',
        'templates/payments/partials/payment_card.html',
        'templates/payments/partials/payment_list_refresh.html',
        'templates/schools/partials/class_table_body.html',
        'templates/students/partials/student_card.html',
        'templates/students/partials/student_table_body.html',
        # Type 3 — Profil/détails
        'templates/students/partials/student_profile_view.html',
        'templates/students/partials/student_profile_edit.html',
        'templates/students/student_detail.html',
        'templates/superadmin/director_create.html',
        'templates/superadmin/school_create.html',
    ]
    
    modified = []
    for fpath in files:
        if update_file(fpath):
            modified.append(fpath)
    
    print("=== Fichiers modifiés ===")
    for f in modified:
        print(f"  ✓ {f}")
    print(f"\nTotal: {len(modified)} fichiers")

if __name__ == '__main__':
    main()