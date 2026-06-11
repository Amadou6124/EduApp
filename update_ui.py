#!/usr/bin/env python3
"""
Remplacer les classes boutons, inputs, badges
par les classes composants (btn-primary, input-field, etc.)

SÉCURITÉ :
- Ne touche PAS aux attributs :class, x-bind:class, hx-*, @click, x-data
- Ne touche PAS aux classes dans les balises <script>
- Backup git fait avant exécution
"""

import re
import os

# Patterns de classes à remplacer (old → new)
REPLACEMENTS = [
    # ── BOUTONS PRIMAIRES ──
    # Pattern générique : bg-brand-blue ... white ... rounded-lg px-4 py-2
    (r'class="bg-brand-blue\s+text-white\s+font-semibold\s+px-5\s+py-2\.5\s+rounded-lg',
     'class="btn-primary'),

    (r'class="bg-brand-blue\s+hover:bg-blue-800\s+text-white\s+font-semibold\s+px-4\s+py-2\s+rounded-lg',
     'class="btn-primary'),

    (r'class="bg-brand-gold\s+hover:bg-yellow-500\s+text-white\s+font-semibold\s+px-5\s+py-2\.5\s+rounded-lg',
     'class="btn-primary'),

    (r'class="bg-brand-gold\s+hover:bg-yellow-500\s+text-white\s+font-semibold\s+px-4\s+py-2(\.5)?\s+rounded-lg',
     'class="btn-primary'),

    (r'class="bg-brand-gold\s+hover:bg-amber-500\s+text-white\s+(font-semibold\s+)?px-4\s+py-2\s+rounded-lg',
     'class="btn-primary'),

    (r'class="bg-brand-gold\s+hover:bg-amber-500\s+text-white\s+(font-semibold\s+)?px-3\s+py-1\.5\s+rounded-lg',
     'class="btn-primary'),

    (r'class="bg-brand-gold\s+hover:bg-yellow-500\s+text-white\s+font-semibold\s+px-5\s+py-2\.5\s+rounded-lg\s+transition\s+shadow-sm\s+min-h-\[44px\]',
     'class="btn-primary'),

    # ── BOUTONS SECONDAIRES ──
    (r'class="flex-1\s+px-4\s+py-2\.5\s+bg-white\s+border\s+border-gray-200\s+text-gray-600\s+text-sm\s+font-medium\s+rounded-lg\s+hover:bg-gray-50\s+transition\s+min-h-\[44px\]',
     'class="btn-secondary flex-1'),

    (r'class="bg-white\s+hover:bg-gray-50\s+text-brand-blue\s+border\s+border-brand-blue\s+font-semibold\s+px-4\s+py-2\.5\s+rounded-lg',
     'class="btn-secondary'),

    (r'class="px-4\s+py-2\s+bg-brand-gold\s+text-white\s+rounded-lg\s+text-sm\s+font-medium\s+hover:bg-amber-500\s+transition',
     'class="btn-primary'),

    # ── BOUTONS DANGER ──
    (r'class="p-2\s+text-gray-400\s+hover:text-red-500\s+hover:bg-red-50\s+rounded-lg',
     'class="btn-ghost'),

    (r'class="bg-red-50\s+border\s+border-red-200\s+rounded-lg\s+px-4\s+py-2(\.5)?\s+text-sm\s+text-red-700',
     'class="'),

    # ── INPUTS ──
    (r'class="w-full\s+border\s+border-gray-300\s+rounded-lg\s+px-[34]\s+py-2\.5\s+text-sm\s+focus:outline-none\s+focus:ring-2\s+focus:ring-brand-blue\s+focus:border-transparent"',
     'class="input-field"'),

    (r'class="w-full\s+border\s+border-gray-300\s+rounded-lg\s+px-3\s+py-2\.5\s+text-sm\s+focus:outline-none\s+focus:ring-2\s+focus:ring-brand-blue"',
     'class="input-field"'),

    (r'class="border\s+border-gray-300\s+rounded-lg\s+px-[34]\s+py-2\.5\s+text-sm\s+focus:outline-none\s+focus:ring-2\s+focus:ring-brand-blue"',
     'class="input-field'),

    (r'class="flex-1\s+min-w-\[200px\]\s+border\s+border-gray-300\s+rounded-lg\s+px-3\s+py-2\.5\s+text-sm\s+focus:outline-none\s+focus:ring-2\s+focus:ring-brand-blue"',
     'class="input-field flex-1 min-w-[200px]'),

    (r'class="w-full\s+px-4\s+py-3\s+pr-11\s+border\s+border-gray-300\s+rounded-xl\s+text-sm\s+focus:outline-none\s+focus:ring-2\s+focus:ring-brand-blue\s+focus:border-brand-blue\s+placeholder:text-gray-400\s+transition"',
     'class="input-field rounded-xl pr-11'),

    # ── SELECTS ──
    (r'class="border\s+border-gray-200\s+rounded-lg\s+px-3\s+py-2\s+text-sm\s+bg-white\s+focus:ring-2\s+focus:ring-brand-gold/40"',
     'class="input-field"'),

    (r'class="border\s+border-gray-200\s+rounded-lg\s+px-3\s+py-2\s+text-sm\s+bg-white\s+focus:outline-none\s+focus:ring-2\s+focus:ring-brand-gold/40"',
     'class="input-field"'),

    (r'class="border\s+border-gray-200\s+rounded-lg\s+px-3\s+py-1\.5\s+text-sm\s+font-semibold\s+text-brand-blue\s+bg-white\s+focus:outline-none\s+focus:ring-2\s+focus:ring-brand-gold/40"',
     'class="input-field'),

    # ── BADGES STATUT PAIEMENT ──
    # Soldé / Succès
    (r'class="px-2\s+py-0\.5\s+rounded-full\s+text-\[10px\]\s+font-medium\s+bg-green-100\s+text-green-700"',
     'class="badge-success"'),

    (r'class="px-3\s+py-1\s+rounded-full\s+text-xs\s+font-medium\s+bg-green-100\s+text-green-700"',
     'class="badge-success"'),

    # Prêt / Partiel / Warning
    (r'class="px-2\s+py-0\.5\s+rounded-full\s+text-\[10px\]\s+font-medium\s+bg-amber-100\s+text-amber-700"',
     'class="badge-warning"'),

    (r'class="px-3\s+py-1\s+rounded-full\s+text-xs\s+font-medium\s+bg-amber-100\s+text-amber-700"',
     'class="badge-warning"'),

    # Notes manquantes / Impayé / Danger
    (r'class="px-2\s+py-0\.5\s+rounded-full\s+text-\[10px\]\s+font-medium\s+bg-red-50\s+text-red-500"',
     'class="badge-danger"'),

    # ── BADGES NIVEAU SCOLAIRE ──
    # Primaire → emerald
    (r'class="inline-flex\s+items-center\s+gap-1\s+px-2\.5\s+py-0\.5\s+rounded-full\s+text-xs\s+font-medium\s+bg-\[\#EAF3DE\]\s+text-\[\#27500A\]"',
     'class="badge-emerald"'),

    # Collège → blue
    (r'class="inline-flex\s+items-center\s+gap-1\s+px-2\.5\s+py-0\.5\s+rounded-full\s+text-xs\s+font-medium\s+bg-\[\#E6F1FB\]\s+text-\[\#0C447C\]"',
     'class="badge-primary"'),

    # Lycée → purple
    (r'class="inline-flex\s+items-center\s+gap-1\s+px-2\.5\s+py-0\.5\s+rounded-full\s+text-xs\s+font-medium\s+bg-\[\#FAEEDA\]\s+text-\[\#633806\]"',
     'class="badge-purple"'),
]

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original = content

    for pattern, replacement in REPLACEMENTS:
        content = re.sub(pattern, replacement, content)

    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

def main():
    modified = []
    for root, dirs, files in os.walk('templates'):
        for file in files:
            if file.endswith('.html'):
                fpath = os.path.join(root, file)
                if process_file(fpath):
                    modified.append(fpath)
    
    print(f"Fichiers modifiés : {len(modified)}")
    for f in modified:
        print(f"  ✓ {f}")

if __name__ == '__main__':
    main()