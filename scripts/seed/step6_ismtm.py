# ÉTAPE 6 — Institut Supérieur de Management et Technologie du Mali (ISMTM)
# Exécuter : python manage.py shell < scripts/seed/step6_ismtm.py
#
# random.seed(456) — reproductible
# Crée : 206 étudiants, 182 parents, 149 paiements inscription
#        6 classes (L1/L2 × 3 filières), 4 professeurs, 18 matières
#        Pas de notes/bulletins — début d'année
# Prérequis : step1 + step2 exécutés

import random
import datetime
from collections import defaultdict
from decimal import Decimal
from datetime import date, timedelta

from django.utils import timezone
from django.contrib.auth.hashers import make_password

from apps.accounts.models import User, Membership
from apps.schools.models import (
    School, SchoolGroup, SchoolYear, Period,
    SchoolClass, Subject, ClassSubject,
)
from apps.students.models import Student, StudentGuardian
from apps.payments.models import Payment

random.seed(456)
NOW = timezone.now()
UTC = datetime.timezone.utc

# ── PARTIE A
groupe_mande = SchoolGroup.objects.get(id=1)
ismtm = School.objects.create(
    name='Institut Supérieur de Management et Technologie du Mali',
    city='Bamako', address='Hamdallaye ACI', country='Mali',
    accounting_enabled=True, group=groupe_mande,
)
print(f'✓ École : {ismtm.name} (id={ismtm.id})')

souleymane = User.objects.create_user(
    phone_number='76000004', password='test123',
    full_name='Souleymane Maïga', role='director', is_active=True,
)
Membership.objects.create(
    user=souleymane, school=ismtm,
    role='director', job_title='Directeur', is_default=True,
)
print(f'✓ Directeur : {souleymane.full_name}')

# ── PARTIE B
annee = SchoolYear.objects.create(
    school=ismtm, name='2025-2026',
    start_date=date(2025,10,1), end_date=date(2026,6,30),
    is_active=True,
)
t1 = Period.objects.create(
    school_year=annee, name='Trimestre 1', order=1,
    period_type='trimester',
    start_date=date(2025,10,1), end_date=date(2026,1,31),
    is_notes_open=True,
)
print(f'✓ Année {annee.name} + T1 en cours créé')

# ── PARTIE C
TEACHERS_DEF = [
    ('76000021','Professeur Diallo Amadou'),
    ('76000022','Professeur Keïta Boubacar'),
    ('76000023','Professeur Sanogo Fatoumata'),
    ('76000024','Professeur Traoré Issiaka'),
]
teacher_users = []
for phone, name in TEACHERS_DEF:
    u = User.objects.create_user(
        phone_number=phone, password='test123',
        full_name=name, role='teacher', is_active=True,
    )
    Membership.objects.create(
        user=u, school=ismtm, role='teacher',
        job_title='Professeur', is_default=True,
    )
    teacher_users.append(u)
t_diallo, t_keita, t_sanogo, t_traore = teacher_users
print(f'✓ {len(teacher_users)} enseignants créés')

SUBJECT_DEFS = [
    ('Comptabilité générale',    'COMPTA-G', '#92400e'),
    ('Mathématiques financières','MATH-F',   '#2563EB'),
    ('Droit des affaires',       'D-AFF',    '#dc2626'),
    ('Économie générale',        'ECO-G',    '#ca8a04'),
    ('Informatique de gestion',  'INFO-G',   '#0891b2'),
    ('Anglais des affaires',     'ANG-AFF',  '#16a34a'),
    ('Communication',            'COMM',     '#6366f1'),
    ('Algorithmique',            'ALGO',     '#7C3AED'),
    ('Programmation',            'PROG',     '#be185d'),
    ('Base de données',          'BDD',      '#0f766e'),
    ('Réseaux et systèmes',      'RESEAU',   '#b45309'),
    ('Mathématiques',            'MATH',     '#1d4ed8'),
    ('Anglais technique',        'ANG-TECH', '#15803d'),
    ('Droit civil',              'D-CIVIL',  '#ef4444'),
    ('Droit pénal',              'D-PENAL',  '#f97316'),
    ('Droit constitutionnel',    'D-CONST',  '#eab308'),
    ('Histoire du droit',        'H-DROIT',  '#84cc16'),
    ('Anglais juridique',        'ANG-JUR',  '#22c55e'),
]
subjects = {}
for name, short, color in SUBJECT_DEFS:
    subjects[name] = Subject.objects.create(
        school=ismtm, name=name, short_name=short, color=color
    )
print(f'✓ {len(subjects)} matières créées')

GESTION_SUBJ = [
    ('Comptabilité générale',    4, t_diallo),
    ('Mathématiques financières',3, t_diallo),
    ('Droit des affaires',       3, t_sanogo),
    ('Économie générale',        3, t_diallo),
    ('Informatique de gestion',  2, t_keita),
    ('Anglais des affaires',     2, t_traore),
    ('Communication',            1, t_traore),
]
INFO_SUBJ = [
    ('Algorithmique',            4, t_keita),
    ('Programmation',            4, t_keita),
    ('Base de données',          3, t_keita),
    ('Réseaux et systèmes',      3, t_keita),
    ('Mathématiques',            3, t_diallo),
    ('Anglais technique',        2, t_traore),
    ('Communication',            1, t_traore),
]
DROIT_SUBJ = [
    ('Droit civil',              4, t_sanogo),
    ('Droit pénal',              3, t_sanogo),
    ('Droit constitutionnel',    3, t_sanogo),
    ('Histoire du droit',        2, t_sanogo),
    ('Droit des affaires',       3, t_sanogo),
    ('Anglais juridique',        2, t_traore),
    ('Communication',            1, t_traore),
]

CLASSES_DEF = [
    ('Licence 1 Gestion',      40, 250_000, GESTION_SUBJ, 100_000),
    ('Licence 2 Gestion',      35, 250_000, GESTION_SUBJ, 100_000),
    ('Licence 1 Informatique', 38, 280_000, INFO_SUBJ,    120_000),
    ('Licence 2 Informatique', 30, 280_000, INFO_SUBJ,    120_000),
    ('Licence 1 Droit',        35, 230_000, DROIT_SUBJ,   100_000),
    ('Licence 2 Droit',        28, 230_000, DROIT_SUBJ,   100_000),
]

classes_meta       = []
cs_by_class        = defaultdict(list)
inscr_fee_by_class = {}

for cname, csize, fee, subj_list, inscr_fee in CLASSES_DEF:
    klass = SchoolClass.objects.create(
        school=ismtm, name=cname, level='superieur',
        annual_fee=fee, max_capacity=csize, is_active=True,
    )
    classes_meta.append((klass, csize, fee, inscr_fee))
    inscr_fee_by_class[klass.id] = inscr_fee
    for i, (sname, coeff, teacher) in enumerate(subj_list, 1):
        cs = ClassSubject.objects.create(
            school_class=klass, subject=subjects[sname],
            coefficient=Decimal(str(coeff)),
            note_system='moyenne_simple',
            teacher=teacher, order=i, is_active=True,
        )
        cs_by_class[klass.id].append(cs)

total_cs = sum(len(v) for v in cs_by_class.values())
print(f'✓ {len(classes_meta)} classes + {total_cs} ClassSubjects créés')

# ── PARTIE D
PRENOMS_M = ['Mamadou','Ibrahim','Seydou','Oumar','Moussa','Boubacar','Abdoulaye',
    'Adama','Modibo','Hamidou','Cheick','Souleymane','Alou','Drissa',
    'Bakary','Lamine','Salif','Daouda','Issa','Sidy','Mory','Fousseyni',
    'Lassana','Tiécoura','Bréhima','Kalilou','Malick','Yacouba','Birama','Sékou']
PRENOMS_F = ['Fatoumata','Aminata','Mariam','Kadiatou','Awa','Rokia','Assitan',
    'Oumou','Hawa','Kadidia','Djénéba','Nana','Bintou','Sira','Fanta',
    'Maimouna','Coumba','Salimata','Nafissa','Korotoumou','Tenin','Niélé',
    'Ramatou','Tantou','Djeneba']
NOMS = ['Coulibaly','Traoré','Diallo','Keïta','Sanogo','Koné','Cissé',
    'Touré','Bamba','Fofana','Kouyaté','Camara','Dembélé','Sylla',
    'Diarra','Sissoko','Konaré','Dansoko','Bagayoko','Mariko',
    'Niaré','Samaké','Konaté','Sidibé','Doumbia','Maïga','Diabaté',
    'Ballo','Bengaly','Diakité']
PRENOMS_P_M = ['Boubakar','Amadou','Kalilou','Alassane','Siaka','Modibo',
               'Cheick','Drissa','Lamine','Youssouf','Oumar','Sékou']
PRENOMS_P_F = ['Djénéba','Oumou','Sira','Tenin','Hawa','Bintou','Niélé',
               'Fanta','Ramatou','Coumba','Salimata','Maimouna']

def random_dob_univ():
    start = date(2000,1,1); end = date(2005,12,31)
    return start + timedelta(days=random.randint(0,(end-start).days))

ismtm_codes = [str(c) for c in random.sample(range(100000,1000000), 206)]
code_idx = 0
student_objs = []

for klass, csize, fee, inscr_fee in classes_meta:
    for _ in range(csize):
        prenom = random.choice(PRENOMS_M if random.random()<0.55 else PRENOMS_F)
        s = Student(
            school=ismtm, school_class=klass,
            full_name=f'{prenom} {random.choice(NOMS)}',
            date_of_birth=random_dob_univ(),
            tuition_fee=fee,
            access_code=ismtm_codes[code_idx],
            is_active=True,
        )
        code_idx += 1
        student_objs.append(s)

students_list = Student.objects.bulk_create(student_objs, batch_size=200)
print(f'✓ {len(students_list)} étudiants créés')

enroll_base = datetime.datetime(2025,10,1,tzinfo=UTC)
for s in students_list:
    s.enrolled_at = enroll_base + timedelta(days=random.randint(0,14))
Student.objects.bulk_update(students_list, ['enrolled_at'], batch_size=200)

parent_hashed_pwd = make_password('test123')
parent_objs = []; guardian_links = []; parent_pool = []

for s in students_list:
    reuse = (len(parent_pool)>0 and random.random()<0.10)
    if reuse:
        pidx = random.choice(parent_pool)
        guardian_links.append((s, pidx, random.choice(['father','mother','guardian'])))
    else:
        prenom_p = random.choice(PRENOMS_P_M if random.random()<0.50 else PRENOMS_P_F)
        phone_p = f'5{random.randint(0,9)}{random.randint(100000,999999)}'
        parent_objs.append(User(
            phone_number=phone_p, password=parent_hashed_pwd,
            full_name=f'{prenom_p} {random.choice(NOMS)}',
            role='parent', is_active=True,
        ))
        new_idx = len(parent_objs)-1
        parent_pool.append(new_idx)
        guardian_links.append((s, new_idx, random.choice(['father','mother'])))

created_parents = User.objects.bulk_create(parent_objs, batch_size=200)
print(f'✓ {len(created_parents)} parents créés')

sg_objs = []; seen_pairs = set()
for student, pidx, rel in guardian_links:
    parent = created_parents[pidx]
    pair = (parent.id, student.id)
    if pair in seen_pairs: continue
    seen_pairs.add(pair)
    sg_objs.append(StudentGuardian(
        guardian=parent, student=student, relationship=rel, is_primary=True,
    ))
StudentGuardian.objects.bulk_create(sg_objs, batch_size=200)
print(f'✓ {len(sg_objs)} liens parent-étudiant créés')

ism_seq = 1; payment_objs = []
pay_start = date(2025,10,1); pay_end = date(2025,10,20)

def rand_date(s,e):
    return s + timedelta(days=random.randint(0,(e-s).days))

for s in students_list:
    if random.random()<0.70:
        inscr = inscr_fee_by_class[s.school_class_id]
        payment_objs.append(Payment(
            student=s, amount=inscr,
            receipt_number=f'ISM-2025-{ism_seq:04d}',
            collected_by=souleymane,
            payment_date=rand_date(pay_start, pay_end),
            is_cancelled=False,
        ))
        ism_seq += 1

Payment.objects.bulk_create(payment_objs, batch_size=500)
total_paid = sum(int(p.amount) for p in payment_objs)
print(f'✓ {len(payment_objs)} paiements inscription ({total_paid:,} FCFA)')

n_gestion = sum(csize for klass,csize,fee,_ in classes_meta if 'Gestion' in klass.name)
n_info    = sum(csize for klass,csize,fee,_ in classes_meta if 'Informatique' in klass.name)
n_droit   = sum(csize for klass,csize,fee,_ in classes_meta if 'Droit' in klass.name)

print()
print('=' * 62)
print('ÉTAPE 6 — RÉSULTAT  ISMTM')
print('=' * 62)
print(f'  École (id)               : {ismtm.id}')
print(f'  Directeur                : {souleymane.full_name}')
print(f'  Enseignants              : {len(teacher_users)}')
print(f'  Matières (Subject)       : {len(subjects)}')
print(f'  Classes                  : {len(classes_meta)}')
print(f'    Licence Gestion        : {n_gestion} étudiants (L1+L2)')
print(f'    Licence Informatique   : {n_info} étudiants (L1+L2)')
print(f'    Licence Droit          : {n_droit} étudiants (L1+L2)')
print(f'  ClassSubjects            : {total_cs}')
print(f'  Étudiants                : {len(students_list)}')
print(f'  Parents                  : {len(created_parents)}')
print(f'  Liens parent-étudiant    : {len(sg_objs)}')
print(f'  Paiements inscription    : {len(payment_objs)} ({total_paid:,} FCFA)')
print(f"  Notes                    : 0  ← début d'année")
print(f"  Bulletins                : 0  ← début d'année")
print(f"  Absences                 : 0  ← cours tout juste commencés")
print('=' * 62)
