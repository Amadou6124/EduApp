# ÉTAPE 2 — Structure École Sundiata Keïta
# Exécuter : python manage.py shell < scripts/seed/step2_sundiata_structure.py
#
# Crée : Promoteur Moussa Coulibaly + Groupe Scolaire Mandé
#        École Sundiata Keïta + Directeur Ibrahim Diarra
#        Année 2025-2026 + 3 Trimestres
#        8 matières + 18 classes (fondamental 1+2) + 6 enseignants + 144 ClassSubjects
# Prérequis : step1 exécuté

from decimal import Decimal
from datetime import date

from django.utils import timezone

from apps.accounts.models import User, Membership
from apps.schools.models import (
    School, SchoolGroup, SchoolYear, Period,
    SchoolClass, Subject, ClassSubject,
)

NOW = timezone.now()

# ── Promoteur + SchoolGroup ────────────────────────────────────────────────
moussa = User.objects.create_user(
    phone_number='76000001', password='test123',
    full_name='Moussa Coulibaly', role='promoter', is_active=True,
)
groupe_mande = SchoolGroup.objects.create(
    name='Groupe Scolaire Mandé',
    owner=moussa,
)
print(f'✓ Promoteur : {moussa.full_name} ({moussa.phone_number})')
print(f'✓ SchoolGroup : {groupe_mande.name} (id={groupe_mande.id})')

# ── École + Directeur ──────────────────────────────────────────────────────
sundiata = School.objects.create(
    name='École Primaire et Fondamentale Sundiata Keïta',
    city='Bamako', address='Quartier du Fleuve', country='Mali',
    accounting_enabled=True, group=groupe_mande,
)
print(f'✓ École : {sundiata.name} (id={sundiata.id})')

ibrahim = User.objects.create_user(
    phone_number='76000002', password='test123',
    full_name='Ibrahim Diarra', role='director',
    is_active=True, school=sundiata,
)
Membership.objects.create(
    user=ibrahim, school=sundiata,
    role='director', job_title='Directeur', is_default=True,
)
print(f'✓ Directeur : {ibrahim.full_name} ({ibrahim.phone_number})')

# ── Année scolaire + Trimestres ────────────────────────────────────────────
annee = SchoolYear.objects.create(
    school=sundiata, name='2025-2026',
    start_date=date(2025, 10, 1), end_date=date(2026, 6, 27),
    is_active=True,
)
PERIODES = [
    ('Trimestre 1', 1, date(2025, 10,  1), date(2025, 12, 20), False),
    ('Trimestre 2', 2, date(2026,  1,  5), date(2026,  3, 28), False),
    ('Trimestre 3', 3, date(2026,  4,  6), date(2026,  6, 27), False),
]
for name, order, sd, ed, notes_open in PERIODES:
    Period.objects.create(
        school_year=annee, name=name, order=order,
        period_type='trimester', start_date=sd, end_date=ed,
        is_notes_open=notes_open,
    )
print(f'✓ Année {annee.name} + 3 trimestres')

# ── 6 Enseignants ──────────────────────────────────────────────────────────
TEACHERS_DEF = [
    ('76000010', 'Aminata Koné'),
    ('76000011', 'Seydou Traoré'),
    ('76000012', 'Fatoumata Diallo'),
    ('76000013', 'Boubacar Sidibé'),
    ('76000014', 'Mariam Coulibaly'),
    ('76000015', 'Oumar Keïta'),
]
teacher_users = []
for phone, name in TEACHERS_DEF:
    u = User.objects.create_user(
        phone_number=phone, password='test123',
        full_name=name, role='teacher', is_active=True,
    )
    Membership.objects.create(
        user=u, school=sundiata, role='teacher',
        job_title='', is_default=True,
    )
    teacher_users.append(u)

t_aminata, t_seydou, t_fatoumata, t_boubacar, t_mariam, t_oumar = teacher_users
print(f'✓ {len(teacher_users)} enseignants créés')

# ── 8 Matières ─────────────────────────────────────────────────────────────
SUBJECT_DEFS = [
    ('Français',           'Fr',       '#4F46E5'),
    ('Mathématiques',      'Maths',    '#EF4444'),
    ('Histoire-Géographie','Hist-Géo', '#F59E0B'),
    ('Sciences naturelles','Sci.Nat',  '#10B981'),
    ('Éducation civique',  'Ed.Civ',   '#8B5CF6'),
    ('Anglais',            'Ang',      '#3B82F6'),
    ('Éducation physique', 'EPS',      '#6B7280'),
    ('Arts plastiques',    'Arts',     '#EC4899'),
]
subjects = {}
for name, short, color in SUBJECT_DEFS:
    subjects[name] = Subject.objects.create(
        school=sundiata, name=name, short_name=short, color=color
    )
print(f'✓ {len(subjects)} matières créées')

# ── 18 Classes + 144 ClassSubjects ────────────────────────────────────────
# Fondamental 1 (1ère→6ème) : Aminata enseigne Fr (1-4), Fatoumata (5-6)
# Fondamental 2 (7ème→9ème) : Fatoumata enseigne Fr+HG
# Matières 1ère-4ème : Aminata=Fr, Seydou=Maths, Fatoumata=HG,
#                      Boubacar=Ed.Civ+Sci.Nat, Mariam=Ang, Oumar=EPS+Arts
# Matières 5ème-9ème : Fatoumata=Fr+HG, Seydou=Maths,
#                      Boubacar=Ed.Civ+Sci.Nat, Mariam=Ang, Oumar=EPS+Arts

CLASSES_DEF = [
    # (nom, level, fee, capacite, prof_fr)
    ('1ère Année A', 'fondamental_1', 50_000, 35, t_aminata),
    ('1ère Année B', 'fondamental_1', 50_000, 33, t_aminata),
    ('2ème Année A', 'fondamental_1', 50_000, 34, t_aminata),
    ('2ème Année B', 'fondamental_1', 50_000, 32, t_aminata),
    ('3ème Année A', 'fondamental_1', 50_000, 33, t_aminata),
    ('3ème Année B', 'fondamental_1', 50_000, 31, t_aminata),
    ('4ème Année A', 'fondamental_1', 50_000, 32, t_aminata),
    ('4ème Année B', 'fondamental_1', 50_000, 30, t_aminata),
    ('5ème Année A', 'fondamental_1', 50_000, 30, t_fatoumata),
    ('5ème Année B', 'fondamental_1', 50_000, 28, t_fatoumata),
    ('6ème Année A', 'fondamental_1', 50_000, 28, t_fatoumata),
    ('6ème Année B', 'fondamental_1', 50_000, 26, t_fatoumata),
    ('7ème Année A', 'fondamental_2', 75_000, 25, t_fatoumata),
    ('7ème Année B', 'fondamental_2', 75_000, 24, t_fatoumata),
    ('8ème Année A', 'fondamental_2', 75_000, 22, t_fatoumata),
    ('8ème Année B', 'fondamental_2', 75_000, 21, t_fatoumata),
    ('9ème Année A', 'fondamental_2', 75_000, 20, t_fatoumata),
    ('9ème Année B', 'fondamental_2', 75_000, 19, t_fatoumata),
]

total_cs = 0
for cname, level, fee, cap, t_francais in CLASSES_DEF:
    klass = SchoolClass.objects.create(
        school=sundiata, name=cname, level=level,
        annual_fee=fee, max_capacity=cap, is_active=True,
    )
    CS = [
        (subjects['Français'],            Decimal('3'), t_francais),
        (subjects['Mathématiques'],        Decimal('3'), t_seydou),
        (subjects['Histoire-Géographie'],  Decimal('2'), t_fatoumata),
        (subjects['Éducation civique'],    Decimal('1'), t_boubacar),
        (subjects['Sciences naturelles'],  Decimal('2'), t_boubacar),
        (subjects['Anglais'],              Decimal('2'), t_mariam),
        (subjects['Éducation physique'],   Decimal('1'), t_oumar),
        (subjects['Arts plastiques'],      Decimal('1'), t_oumar),
    ]
    for i, (subj, coeff, teacher) in enumerate(CS, 1):
        ClassSubject.objects.create(
            school_class=klass, subject=subj,
            coefficient=coeff, note_system='moyenne_simple',
            teacher=teacher, order=i, is_active=True,
        )
        total_cs += 1

print(f'✓ {len(CLASSES_DEF)} classes + {total_cs} ClassSubjects créés')
print()
print('=' * 50)
print('ÉTAPE 2 — RÉSULTAT Sundiata Keïta')
print('=' * 50)
print(f'  SchoolGroup id : {groupe_mande.id}')
print(f'  École id       : {sundiata.id}')
print(f'  Enseignants    : {len(teacher_users)}')
print(f'  Matières       : {len(subjects)}')
print(f'  Classes        : {len(CLASSES_DEF)}')
print(f'  ClassSubjects  : {total_cs}')
print('=' * 50)
