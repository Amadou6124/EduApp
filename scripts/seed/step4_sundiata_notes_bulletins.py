# ÉTAPE 4 — Notes + Bulletins Sundiata Keïta
# Exécuter : python manage.py shell < scripts/seed/step4_sundiata_notes_bulletins.py
#
# random.seed(42) → reproductible
# Note.unique_together = (student, class_subject, period, position)
# devoir position=1 / composition position=2
# auto_now champs (modified_at) : settés explicitement (bulk_create bypass)
# Crée : ~24 144 notes, 1 509 bulletins, ~12 072 lignes bulletin
# Prérequis : step1 + step2 + step3 exécutés

import random
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from django.utils import timezone

from apps.accounts.models import User
from apps.schools.models import (
    School, SchoolClass, ClassSubject, Period,
    Note, Bulletin, BulletinLine, BulletinConfig,
)
from apps.students.models import Student

random.seed(42)
NOW = timezone.now()

sundiata = School.objects.get(name__icontains='Sundiata')
ibrahim  = User.objects.get(phone_number='76000002')

students = list(
    Student.objects.filter(school=sundiata, is_active=True)
    .select_related('school_class').order_by('id')
)
periods = list(
    Period.objects.filter(school_year__school=sundiata).order_by('order')
)
class_subjects_all = list(
    ClassSubject.objects
    .filter(school_class__school=sundiata, is_active=True)
    .select_related('subject', 'teacher', 'school_class')
    .order_by('school_class_id', 'order', 'subject__name')
)

cs_by_class = defaultdict(list)
for cs in class_subjects_all:
    cs_by_class[cs.school_class_id].append(cs)

students_by_class = defaultdict(list)
for s in students:
    students_by_class[s.school_class_id].append(s)

config, _ = BulletinConfig.objects.get_or_create(school=sundiata, defaults={
    'republic_line1': 'REPUBLIQUE DU MALI',
    'republic_line2': 'UN PEUPLE - UN BUT - UNE FOI',
    'ministry_line1': "MINISTERE DE L'EDUCATION NATIONALE",
    'bulletin_title': 'RELEVE DE NOTES',
    'footer_left':    'Le Parent / Tuteur',
    'footer_right':   'Le Directeur',
})

# ── Profil de base par élève ───────────────────────────────────────────────
n = len(students)
profile_pool = (
    [('excellent', 16.5, 20.0)] * int(0.15 * n) +
    [('passable',  10.0, 15.5)] * int(0.60 * n) +
    [('weak',       6.0,  9.5)] * (n - int(0.15 * n) - int(0.60 * n))
)
random.shuffle(profile_pool)

base_score = {}
for s, (_, rmin, rmax) in zip(students, profile_pool):
    base_score[s.id] = random.uniform(rmin, rmax)


def gen_note(base):
    v = base + random.uniform(-1.0, 1.0)
    return round(max(0.0, min(20.0, v)), 1)


def mention(avg):
    if avg >= 16: return 'Très bien'
    if avg >= 14: return 'Bien'
    if avg >= 12: return 'Assez bien'
    if avg >= 10: return 'Passable'
    return 'Insuffisant'


# ── Génération notes + bulletins ───────────────────────────────────────────
all_note_objs      = []
all_bulletin_objs  = []
bulletin_map       = {}
class_period_avgs  = defaultdict(list)
cs_period_avgs     = defaultdict(list)

for period in periods:
    for klass_id, cs_list in cs_by_class.items():
        class_students = students_by_class[klass_id]
        if not cs_list or not class_students:
            continue
        total_coeff = sum(cs.coefficient for cs in cs_list) or Decimal('1')

        for student in class_students:
            base  = base_score[student.id]
            wsum  = Decimal('0')
            blines = []

            for cs in cs_list:
                dev_val  = gen_note(base)
                comp_val = gen_note(base)
                entered  = cs.teacher or ibrahim

                all_note_objs.append(Note(
                    student=student, class_subject=cs, period=period,
                    note_type='devoir', position=1,
                    value=Decimal(str(dev_val)),
                    entered_by=entered, entered_at=NOW, modified_at=NOW,
                ))
                all_note_objs.append(Note(
                    student=student, class_subject=cs, period=period,
                    note_type='composition', position=2,
                    value=Decimal(str(comp_val)),
                    entered_by=entered, entered_at=NOW, modified_at=NOW,
                ))

                final_avg = Decimal(str(round((dev_val + comp_val) / 2, 2)))
                weighted  = (final_avg * cs.coefficient).quantize(
                    Decimal('0.01'), rounding=ROUND_HALF_UP
                )
                wsum += weighted
                blines.append({
                    'cs': cs, 'dev': Decimal(str(dev_val)),
                    'comp': Decimal(str(comp_val)), 'final': final_avg,
                    'weighted': weighted, 'mention': mention(float(final_avg)),
                    'rank_subj': None,
                })
                cs_period_avgs[(cs.id, period.id)].append(
                    (student.id, float(final_avg))
                )

            general_avg = (wsum / total_coeff).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
            b = Bulletin(
                student=student, period=period,
                school_class_id=klass_id,
                generated_at=NOW, generated_by=ibrahim,
                is_published=True, published_at=NOW,
                general_average=general_avg,
                appreciation=mention(float(general_avg)),
                is_cancelled=False,
            )
            all_bulletin_objs.append(b)
            bulletin_map[(student.id, period.id)] = {'bobj': b, 'lines': blines}
            class_period_avgs[(klass_id, period.id)].append(
                (student.id, float(general_avg))
            )

# ── Notes → DB ────────────────────────────────────────────────────────────
Note.objects.bulk_create(all_note_objs, batch_size=2000)
print(f'✓ {len(all_note_objs)} notes créées')

# ── Bulletins → DB ────────────────────────────────────────────────────────
created_bulletins = Bulletin.objects.bulk_create(all_bulletin_objs, batch_size=500)

# Rangs par classe/période
for (class_id, period_id), avgs in class_period_avgs.items():
    sorted_avgs = sorted(avgs, key=lambda x: x[1], reverse=True)
    first_avg   = Decimal(str(round(sorted_avgs[0][1], 2))) if sorted_avgs else None
    class_size  = len(sorted_avgs)
    rank_map    = {sid: r + 1 for r, (sid, _) in enumerate(sorted_avgs)}
    for (sid, pid), bdata in bulletin_map.items():
        b = bdata['bobj']
        if pid == period_id and b.school_class_id == class_id:
            b.rank         = rank_map.get(sid)
            b.class_size   = class_size
            b.first_average = first_avg

Bulletin.objects.bulk_update(
    all_bulletin_objs, ['rank', 'class_size', 'first_average'], batch_size=500
)
print(f'✓ {len(created_bulletins)} bulletins créés avec rangs')

# ── BulletinLines → DB ────────────────────────────────────────────────────
# Rangs par matière/période
for (cs_id, period_id), avgs in cs_period_avgs.items():
    sorted_avgs = sorted(avgs, key=lambda x: x[1], reverse=True)
    rank_map    = {sid: r + 1 for r, (sid, _) in enumerate(sorted_avgs)}
    for (sid, pid), bdata in bulletin_map.items():
        if pid != period_id:
            continue
        for line in bdata['lines']:
            if line['cs'].id == cs_id:
                line['rank_subj'] = rank_map.get(sid)

all_bline_objs = []
for b in created_bulletins:
    bdata = bulletin_map.get((b.student_id, b.period_id))
    if not bdata:
        continue
    for line in bdata['lines']:
        all_bline_objs.append(BulletinLine(
            bulletin=b, class_subject=line['cs'],
            devoir_average=line['dev'], compo_grade=line['comp'],
            final_average=line['final'], weighted_grade=line['weighted'],
            appreciation=line['mention'], rank_in_subject=line['rank_subj'],
        ))

BulletinLine.objects.bulk_create(all_bline_objs, batch_size=2000)
print(f'✓ {len(all_bline_objs)} lignes bulletin créées')
print()
print('=' * 50)
print('ÉTAPE 4 — RÉSULTAT Sundiata Keïta')
print('=' * 50)
print(f'  Notes      : {len(all_note_objs)}')
print(f'  Bulletins  : {len(created_bulletins)}')
print(f'  Lignes     : {len(all_bline_objs)}')
print('=' * 50)
