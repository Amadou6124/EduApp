#!/usr/bin/env python3
"""Moderniser les 14 états vides principaux."""
import os

def replace_in_file(filepath, old, new):
    with open(filepath, 'r') as f:
        c = f.read()
    if old in c:
        c = c.replace(old, new)
        with open(filepath, 'w') as f:
            f.write(c)
        return True
    return False

# ── 1. students/partials/student_table_body.html — "Aucun élève trouvé" ──
old1 = '''    <div class="text-center py-16 text-gray-400">
      <p class="text-sm">Aucun élève trouvé</p>
    </div>'''

new1 = '''    <div class="flex flex-col items-center justify-center py-16 px-8 text-center">
      <div class="w-14 h-14 rounded-2xl bg-gray-100 flex items-center justify-center mb-4">
        <i data-lucide="users" class="w-7 h-7 text-gray-400"></i>
      </div>
      <h3 class="text-sm font-semibold text-gray-900 mb-1">Aucun élève trouvé</h3>
      <p class="text-sm text-gray-500 max-w-xs mb-5 leading-relaxed">
        Commencez par inscrire vos élèves dans une classe.
      </p>
      <a href="{% url 'students:list' %}" class="btn-primary text-sm">
        <i data-lucide="plus" class="w-4 h-4"></i>
        Inscrire un élève
      </a>
    </div>'''

# ── 2. schools/partials/class_table_body.html — "Aucune classe créée" (cards view) ──
old2 = '''    <div class="text-center py-20">
      <p class="font-medium text-gray-500 text-lg">{% trans "Aucune classe créée" %}</p>
    </div>'''

new2 = '''    <div class="flex flex-col items-center justify-center py-16 px-8 text-center">
      <div class="w-14 h-14 rounded-2xl bg-gray-100 flex items-center justify-center mb-4">
        <i data-lucide="school" class="w-7 h-7 text-gray-400"></i>
      </div>
      <h3 class="text-sm font-semibold text-gray-900 mb-1">{% trans "Aucune classe créée" %}</h3>
      <p class="text-sm text-gray-500 max-w-xs mb-5 leading-relaxed">
        {% trans "Créez votre première classe pour commencer." %}
      </p>
      <button @click="showAddModal = true" class="btn-primary text-sm">
        <i data-lucide="plus" class="w-4 h-4"></i>
        {% trans "Créer une classe" %}
      </button>
    </div>'''

# ── 3. schools/partials/class_table_body.html — "Aucune classe" (table view) ──
old3 = '''    <div class="text-center py-16 text-gray-400">
      <p class="font-medium">{% trans "Aucune classe" %}</p>
    </div>'''

new3 = '''    <div class="flex flex-col items-center justify-center py-12 px-8 text-center">
      <div class="w-14 h-14 rounded-2xl bg-gray-100 flex items-center justify-center mb-4">
        <i data-lucide="school" class="w-7 h-7 text-gray-400"></i>
      </div>
      <h3 class="text-sm font-semibold text-gray-900 mb-1">{% trans "Aucune classe" %}</h3>
      <p class="text-sm text-gray-500 max-w-xs mb-5 leading-relaxed">
        {% trans "Créez votre première classe." %}
      </p>
      <button @click="showAddModal = true" class="btn-primary text-sm">
        <i data-lucide="plus" class="w-4 h-4"></i>
        {% trans "Créer une classe" %}
      </button>
    </div>'''

# ── 4. notes/notes_dashboard.html — "Aucune année scolaire configurée" ──
old4 = '''  <div class="flex flex-col items-center justify-center py-20 text-center">
    <div class="w-16 h-16 rounded-full bg-brand-gold/20 flex items-center justify-center mb-4">
      <svg class="w-8 h-8 text-brand-gold" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/>
      </svg>
    </div>
    <h2 class="text-lg font-semibold text-gray-700 mb-2">Aucune année scolaire configurée</h2>
    <p class="text-gray-500 text-sm mb-4">
      Configurez d'abord une année scolaire et ses périodes dans les paramètres.
    </p>
    <a href="{% url 'settings:school-years' %}"
       class="px-4 py-2 bg-brand-gold text-white rounded-lg text-sm font-medium hover:bg-amber-500 transition">
      Configurer les années scolaires
    </a>
  </div>'''

new4 = '''  <div class="flex flex-col items-center justify-center py-16 px-8 text-center">
    <div class="w-14 h-14 rounded-2xl bg-gray-100 flex items-center justify-center mb-4">
      <i data-lucide="calendar" class="w-7 h-7 text-gray-400"></i>
    </div>
    <h3 class="text-sm font-semibold text-gray-900 mb-1">Aucune année scolaire configurée</h3>
    <p class="text-sm text-gray-500 max-w-xs mb-5 leading-relaxed">
      Configurez d'abord une année scolaire et ses périodes dans les paramètres.
    </p>
    <a href="{% url 'settings:school-years' %}" class="btn-primary text-sm">
      <i data-lucide="settings" class="w-4 h-4"></i>
      Configurer les années scolaires
    </a>
  </div>'''

# ── 5. notes/notes_dashboard.html — "Aucune classe active" ──
old5 = '''  <div class="text-center py-16 text-gray-400">
    <p class="text-sm">Aucune classe active dans cette école.</p>
  </div>'''

new5 = '''  <div class="flex flex-col items-center justify-center py-12 px-8 text-center">
    <div class="w-14 h-14 rounded-2xl bg-gray-100 flex items-center justify-center mb-4">
      <i data-lucide="school" class="w-7 h-7 text-gray-400"></i>
    </div>
    <h3 class="text-sm font-semibold text-gray-900 mb-1">Aucune classe active</h3>
    <p class="text-sm text-gray-500 max-w-xs leading-relaxed">
      Aucune classe active dans cette école.
    </p>
  </div>'''

# ── 6. notes/notes_dashboard.html — "Aucune période configurée" ──
old6 = '''<div class="bg-white rounded-xl border border-dashed border-gray-200 p-8 text-center">
  <p class="text-gray-500 text-sm">
    Aucune période configurée pour l'année {{ active_year.name }}.
  </p>
  <a href="{% url 'settings:school-year-periods' active_year.pk %}"
     class="inline-block mt-3 text-sm text-brand-blue hover:underline">
    Configurer les périodes →
  </a>
</div>'''

new6 = '''<div class="flex flex-col items-center justify-center py-12 px-8 text-center">
  <div class="w-14 h-14 rounded-2xl bg-gray-100 flex items-center justify-center mb-4">
    <i data-lucide="layers" class="w-7 h-7 text-gray-400"></i>
  </div>
  <h3 class="text-sm font-semibold text-gray-900 mb-1">Aucune période configurée</h3>
  <p class="text-sm text-gray-500 max-w-xs mb-5 leading-relaxed">
    Aucune période configurée pour l'année {{ active_year.name }}.
  </p>
  <a href="{% url 'settings:school-year-periods' active_year.pk %}" class="btn-primary text-sm">
    <i data-lucide="settings" class="w-4 h-4"></i>
    Configurer les périodes
  </a>
</div>'''

# ── 7. notes/notes_class.html — "Aucune matière assignée" ──
old7 = '''  <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-12 text-center">
    <div class="w-14 h-14 rounded-full bg-gray-100 flex items-center justify-center mx-auto mb-4">
      <svg class="w-7 h-7 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/>
      </svg>
    </div>
    <h2 class="text-lg font-semibold text-gray-700 mb-2">Aucune matière assignée</h2>
    <p class="text-sm text-gray-400 mb-4">
      Cette classe n'a aucune matière configurée pour la saisie des notes.
    </p>
    <a href="{% url 'settings:subjects' %}"
       class="inline-block px-4 py-2 bg-brand-gold text-white rounded-lg text-sm font-medium hover:bg-amber-500 transition">
      Configurer les matières
    </a>
  </div>'''

new7 = '''  <div class="flex flex-col items-center justify-center py-16 px-8 text-center">
    <div class="w-14 h-14 rounded-2xl bg-gray-100 flex items-center justify-center mx-auto mb-4">
      <i data-lucide="layers" class="w-7 h-7 text-gray-400"></i>
    </div>
    <h3 class="text-sm font-semibold text-gray-900 mb-1">Aucune matière assignée</h3>
    <p class="text-sm text-gray-500 max-w-xs mb-5 leading-relaxed">
      Cette classe n'a aucune matière configurée pour la saisie des notes.
    </p>
    <a href="{% url 'settings:subjects' %}" class="btn-primary text-sm">
      <i data-lucide="settings" class="w-4 h-4"></i>
      Configurer les matières
    </a>
  </div>'''

# ── 8. notes/partials/notes_table.html — "Aucun élève dans cette classe" ──
old8 = '''  {# ── Vide : aucun élève ──────────────────────────────────────── #}
  <div class="bg-white rounded-xl border border-gray-200 p-8 text-center">
    <p class="text-sm text-gray-400">Aucun élève dans cette classe.</p>
  </div>'''

new8 = '''  {# ── Vide : aucun élève ──────────────────────────────────────── #}
  <div class="flex flex-col items-center justify-center py-12 px-8 text-center">
    <div class="w-14 h-14 rounded-2xl bg-gray-100 flex items-center justify-center mx-auto mb-4">
      <i data-lucide="users" class="w-7 h-7 text-gray-400"></i>
    </div>
    <h3 class="text-sm font-semibold text-gray-900 mb-1">Aucun élève</h3>
    <p class="text-sm text-gray-500 max-w-xs leading-relaxed">
      Aucun élève dans cette classe.
    </p>
  </div>'''

# ── 9. dashboard/dashboard.html — "Aucune inscription cette année" (empty chart) ──
old9 = '''    <div class="flex flex-col items-center justify-center h-48 text-gray-400">
      <p class="text-sm">Aucune inscription cette année.</p>
      <a href="{% url 'students:list' %}" class="text-xs text-brand-blue hover:underline mt-1">Inscrire un élève →</a>
    </div>'''

new9 = '''    <div class="flex flex-col items-center justify-center h-48 text-center px-4">
      <div class="w-12 h-12 rounded-2xl bg-gray-100 flex items-center justify-center mb-3">
        <i data-lucide="users" class="w-6 h-6 text-gray-400"></i>
      </div>
      <p class="text-sm text-gray-500 mb-2">Aucune inscription cette année</p>
      <a href="{% url 'students:list' %}" class="text-xs font-medium text-brand-blue hover:underline">Inscrire un élève →</a>
    </div>'''

# ── 10. dashboard/dashboard.html — "Aucun paiement enregistré" (empty chart) ──
old10 = '''    <div class="flex flex-col items-center justify-center h-48 text-gray-400">
      <p class="text-sm">Aucun paiement enregistré.</p>
      <a href="{% url 'payments:dashboard' %}" class="text-xs text-brand-blue hover:underline mt-1">Enregistrer un paiement →</a>
    </div>'''

new10 = '''    <div class="flex flex-col items-center justify-center h-48 text-center px-4">
      <div class="w-12 h-12 rounded-2xl bg-gray-100 flex items-center justify-center mb-3">
        <i data-lucide="credit-card" class="w-6 h-6 text-gray-400"></i>
      </div>
      <p class="text-sm text-gray-500 mb-2">Aucun paiement enregistré</p>
      <a href="{% url 'payments:dashboard' %}" class="text-xs font-medium text-brand-blue hover:underline">Enregistrer →</a>
    </div>'''

# ── 11. dashboard/partials/activity_feed.html — "Aucune activité récente" ──
old11 = '''    <div class="text-center py-8 text-gray-400">
      <p class="text-sm">Aucune activité récente.</p>
    </div>'''

new11 = '''    <div class="flex flex-col items-center justify-center py-8 text-center">
      <div class="w-12 h-12 rounded-2xl bg-gray-100 flex items-center justify-center mb-3">
        <i data-lucide="activity" class="w-6 h-6 text-gray-400"></i>
      </div>
      <p class="text-sm text-gray-500">Aucune activité récente</p>
    </div>'''

# ── 12. dashboard/partials/class_health.html — "Aucune donnée disponible" ──
old12 = '''    <div class="text-center py-8 text-gray-400">
      <p class="text-sm">Aucune donnée disponible pour cette période.</p>
    </div>'''

new12 = '''    <div class="flex flex-col items-center justify-center py-8 text-center">
      <div class="w-12 h-12 rounded-2xl bg-gray-100 flex items-center justify-center mb-3">
        <i data-lucide="bar-chart-2" class="w-6 h-6 text-gray-400"></i>
      </div>
      <p class="text-sm text-gray-500">Aucune donnée disponible pour cette période</p>
    </div>'''

# ── 13. payments/partials/payment_list_refresh.html — "Aucun résultat" (search) ──
old13 = '''      <p class="text-sm font-medium text-gray-500">Aucun résultat</p>
      <p class="text-xs text-gray-400 mt-1">Essayez de modifier vos filtres</p>'''

new13 = '''      <div class="w-12 h-12 rounded-2xl bg-gray-100 flex items-center justify-center mx-auto mb-3">
        <i data-lucide="search" class="w-6 h-6 text-gray-400"></i>
      </div>
      <p class="text-sm font-medium text-gray-900 mb-0.5">Aucun résultat</p>
      <p class="text-xs text-gray-500">Essayez de modifier vos filtres</p>'''

# ── 14. payments/partials/payment_timeline.html — "Aucun paiement enregistré" ──
old14 = '''    <p class="text-sm text-gray-400 text-center py-8">Aucun paiement enregistré</p>'''

new14 = '''    <div class="flex flex-col items-center justify-center py-8 text-center">
      <div class="w-12 h-12 rounded-2xl bg-gray-100 flex items-center justify-center mb-3">
        <i data-lucide="credit-card" class="w-6 h-6 text-gray-400"></i>
      </div>
      <p class="text-sm text-gray-500">Aucun paiement enregistré</p>
    </div>'''

# ── 15. bulletins/partials/rankings_tab.html — "Aucun bulletin généré" ──
old15 = '''      Aucun bulletin généré pour cette classe sur cette période.'''

new15 = '''      <div class="flex flex-col items-center justify-center py-8 text-center">
        <div class="w-12 h-12 rounded-2xl bg-gray-100 flex items-center justify-center mb-3">
          <i data-lucide="award" class="w-6 h-6 text-gray-400"></i>
        </div>
        <p class="text-sm text-gray-500">Aucun bulletin généré pour cette classe sur cette période.</p>
      </div>'''

replacements = [
    ('templates/students/partials/student_table_body.html', old1, new1),
    ('templates/schools/partials/class_table_body.html', old2, new2),
    ('templates/schools/partials/class_table_body.html', old3, new3),
    ('templates/notes/notes_dashboard.html', old4, new4),
    ('templates/notes/notes_dashboard.html', old5, new5),
    ('templates/notes/notes_dashboard.html', old6, new6),
    ('templates/notes/notes_class.html', old7, new7),
    ('templates/notes/partials/notes_table.html', old8, new8),
    ('templates/dashboard/dashboard.html', old9, new9),
    ('templates/dashboard/dashboard.html', old10, new10),
    ('templates/dashboard/partials/activity_feed.html', old11, new11),
    ('templates/dashboard/partials/class_health.html', old12, new12),
    ('templates/payments/partials/payment_list_refresh.html', old13, new13),
    ('templates/payments/partials/payment_timeline.html', old14, new14),
    ('templates/bulletins/partials/rankings_tab.html', old15, new15),
]

modified = set()
for fpath, old, new in replacements:
    if replace_in_file(fpath, old, new):
        modified.add(fpath)

print("Fichiers modifiés :")
for f in sorted(modified):
    print(f"  ✓ {f}")
print(f"\nTotal : {len(modified)} fichiers")