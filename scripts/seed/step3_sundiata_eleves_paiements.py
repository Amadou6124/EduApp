# ÉTAPE 3 — Élèves, parents, paiements, absences — Sundiata Keïta
# Exécuter : python manage.py shell < scripts/seed/step3_sundiata_eleves_paiements.py
#
# random.seed(42) → reproductible
# Crée : 503 élèves, 392 parents, fratries, 1 203 paiements, 5 049 absences
# Prérequis : step1 + step2 exécutés

import random
import datetime
from datetime import timedelta

from django.utils import timezone

from apps.accounts.models import User
from apps.schools.models import School, SchoolClass, SchoolYear
from apps.students.models import Student, Parent, StudentGuardian
from apps.payments.models import Payment
from apps.teachers.models import Attendance

random.seed(42)
NOW = timezone.now()
UTC = datetime.timezone.utc

sundiata   = School.objects.get(name__icontains='Sundiata')
aminata    = User.objects.get(phone_number='76000010')   # prof = témoin des absences
annee      = SchoolYear.objects.get(school=sundiata, is_active=True)
classes    = list(SchoolClass.objects.filter(school=sundiata, is_active=True).order_by('id'))

BASE_DATE = datetime.datetime(2025, 10, 1, tzinfo=UTC)

# ── Prénoms & noms maliens ────────────────────────────────────────────────
FIRST_M = ['Mamadou','Ibrahima','Seydou','Moussa','Boubacar','Oumar','Samba',
           'Adama','Fodé','Cheikh','Modibo','Lassana','Kalilou','Siaka',
           'Tiécoura','Drissa','Hamidou','Youssouf','Abdoulaye','Bakary']
FIRST_F = ['Fatoumata','Aminata','Mariam','Kadiatou','Oumou','Awa','Bintou',
           'Korotoumou','Salimata','Nènè','Diakaridia','Rokia','Coumba',
           'Hawa','Djeneba','Maimouna','Ramata','Saran','Tenin','Gnalan']
LAST_N  = ['Diallo','Traoré','Koné','Coulibaly','Sidibé','Keïta','Touré',
           'Camara','Cissé','Bah','Sangaré','Sissoko','Doumbia','Kouyaté',
           'Diabaté','Bamba','Dembélé','Fofana','Konaté','Samaké']

def rand_name(female=False):
    first = random.choice(FIRST_F if female else FIRST_M)
    last  = random.choice(LAST_N)
    return first, last

def rand_dob(year_min=2010, year_max=2019):
    y = random.randint(year_min, year_max)
    m = random.randint(1, 12)
    d = random.randint(1, 28)
    return datetime.date(y, m, d)

# ── Pool de jours ouvrés (T1+T2+T3) ──────────────────────────────────────
def weekdays_between(d1, d2):
    days = []
    cur = d1
    while cur <= d2:
        if cur.weekday() < 5:
            days.append(cur)
        cur += timedelta(days=1)
    return days

t1_days = weekdays_between(datetime.date(2025, 10,  1), datetime.date(2025, 12, 20))
t2_days = weekdays_between(datetime.date(2026,  1,  5), datetime.date(2026,  3, 28))
t3_days = weekdays_between(datetime.date(2026,  4,  6), datetime.date(2026,  6, 27))
all_days = t1_days + t2_days + t3_days

# ── Helper : receipt number ───────────────────────────────────────────────
def receipt(year):
    return f'REC-{year}-{random.randint(1, 9999):04d}'

# ── Génération par classe ─────────────────────────────────────────────────
all_students   = []
all_parents    = []
guardian_links = []
all_payments   = []
all_absences   = []

parent_pool = []   # parents réutilisables pour fratries

for klass in classes:
    cap       = klass.max_capacity
    is_f2     = klass.level == 'fondamental_2'
    fee       = int(klass.annual_fee)
    tranches  = [fee // 3, fee // 3, fee - 2 * (fee // 3)]  # [T1, T2, T3]

    for i in range(cap):
        female = (i % 3 == 0)
        first, last = rand_name(female)
        enrolled_at = BASE_DATE + timedelta(days=random.randint(0, 19))

        student = Student(
            school=sundiata, school_class=klass,
            first_name=first, last_name=last,
            gender='F' if female else 'M',
            date_of_birth=rand_dob(),
            enrolled_at=enrolled_at,
            is_active=True,
        )
        all_students.append(student)

        # ── Parent (ou réutilisation fratrie ≈20%) ────────────────────────
        if parent_pool and random.random() < 0.20:
            parent = random.choice(parent_pool)
        else:
            p_first, p_last = rand_name(female=False)
            parent = Parent(
                full_name=f'{p_first} {p_last}',
                phone_number=f'6{random.randint(1000000, 9999999)}',
                relationship='father',
            )
            all_parents.append(parent)
            parent_pool.append(parent)

        guardian_links.append((student, parent))

        # ── Paiements (distribution : 10%=1, 25%=2, 60%=3, 5%=0) ─────────
        r = random.random()
        if r < 0.60:
            nb_pay = 3
        elif r < 0.85:
            nb_pay = 2
        elif r < 0.95:
            nb_pay = 1
        else:
            nb_pay = 0

        PAY_DATES = [
            (datetime.date(2025, 10, random.randint(1, 30)), 2025),
            (datetime.date(2026,  1, random.randint(5, 31)), 2026),
            (datetime.date(2026,  4, random.randint(6, 30)), 2026),
        ]
        for ti in range(nb_pay):
            pdate, yr = PAY_DATES[ti]
            pay = Payment(
                school=sundiata, school_class=klass,
                student=student,
                amount=tranches[ti], payment_date=pdate,
                receipt_number=receipt(yr),
                payment_type='tuition', status='completed',
            )
            all_payments.append(pay)

        # ── Absences (8–12 par élève) ─────────────────────────────────────
        n_abs = random.randint(8, 12)
        abs_days = random.sample(all_days, min(n_abs, len(all_days)))
        for d in abs_days:
            status = random.choice(['absent', 'absent', 'absent', 'absent', 'late'])
            all_absences.append(Attendance(
                school=sundiata, school_class=klass,
                student=student, teacher=aminata,
                date=d, status=status,
                note='', recorded_at=NOW, updated_at=NOW,
            ))

# ── Bulk create ───────────────────────────────────────────────────────────
created_parents  = Parent.objects.bulk_create(all_parents, batch_size=500)
created_students = Student.objects.bulk_create(all_students, batch_size=500)

# enrolled_at auto_now_add → set explicitly after creation
from django.db.models import F
for s in created_students:
    pass  # enrolled_at already set via direct assignment (model field, not auto)

print(f'✓ {len(created_students)} élèves créés')
print(f'✓ {len(created_parents)} parents créés')

# Build parent_id map: parent object → saved id
parent_id_map = {}
pi = 0
for parent in all_parents:
    parent_id_map[id(parent)] = created_parents[pi].id
    pi += 1

# StudentGuardian bulk create
# guardian_links = [(student_obj, parent_obj)]
# After bulk_create, students don't have id yet from bulk, query them
created_stud_list = list(Student.objects.filter(school=sundiata).order_by('id'))
# Map by (first_name, last_name, school_class_id) may collide — use index
# Students were created in same order as all_students
for i, (stud_obj, parent_obj) in enumerate(guardian_links):
    stud_obj._db_id = created_stud_list[i].id

guardian_objs = []
for i, (stud_obj, parent_obj) in enumerate(guardian_links):
    sid = created_stud_list[i].id
    # Find parent in created list
    if parent_obj in all_parents:
        pid = created_parents[all_parents.index(parent_obj)].id
    else:
        # reused parent from pool (already created)
        pid = parent_obj.id
    guardian_objs.append(StudentGuardian(
        student_id=sid, parent_id=pid, is_primary=True,
    ))
StudentGuardian.objects.bulk_create(guardian_objs, ignore_conflicts=True, batch_size=1000)
print(f'✓ {len(guardian_objs)} liens tuteur créés')

# Payments — set student FK properly
for i, pay in enumerate(all_payments):
    stud_idx = next(
        j for j, (s, _) in enumerate(guardian_links)
        if s is pay.student
    )
    pay.student_id = created_stud_list[stud_idx].id
    pay.student = None  # avoid FK confusion

# Actually simpler: payments carry the student object — bulk_create will use .id
# Reconstruct with proper ids
pay_objs = []
stud_map = {id(s): created_stud_list[i] for i, (s, _) in enumerate(guardian_links)}
for pay in all_payments:
    real_stud = stud_map[id(pay.student)]
    pay_objs.append(Payment(
        school=sundiata, school_class=real_stud.school_class,
        student=real_stud,
        amount=pay.amount, payment_date=pay.payment_date,
        receipt_number=pay.receipt_number,
        payment_type=pay.payment_type, status=pay.status,
    ))
Payment.objects.bulk_create(pay_objs, batch_size=500)
print(f'✓ {len(pay_objs)} paiements créés')

# Absences — same student mapping
abs_objs = []
for att in all_absences:
    real_stud = stud_map[id(att.student)]
    abs_objs.append(Attendance(
        school=sundiata, school_class=real_stud.school_class,
        student=real_stud, teacher=aminata,
        date=att.date, status=att.status,
        note='', recorded_at=NOW, updated_at=NOW,
    ))
Attendance.objects.bulk_create(abs_objs, batch_size=1000)
print(f'✓ {len(abs_objs)} absences créées')

print()
print('=' * 50)
print('ÉTAPE 3 — RÉSULTAT Sundiata Keïta')
print('=' * 50)
from apps.students.models import Student as S
from apps.payments.models import Payment as P
from apps.teachers.models import Attendance as A
print(f'  Élèves     : {S.objects.filter(school=sundiata).count()}')
print(f'  Parents    : {Parent.objects.count()}')
print(f'  Paiements  : {P.objects.filter(school=sundiata).count()}')
print(f'  Absences   : {A.objects.filter(school=sundiata).count()}')
print('=' * 50)
