# ÉTAPE 5 — Lycée Privé Excellence Sankara
# Exécuter : python manage.py shell < scripts/seed/step5_sankara.py
#
# random.seed(123) — reproductible
# Note.unique_together = (student, class_subject, period, position)
#   → devoir position=1 / composition position=2
# Bulletins T1+T2 uniquement — T3 : notes 40% élèves, pas de bulletins
# Crée : 244 élèves, 212 parents, 378 paiements, 2 450 absences,
#        8 546 notes, 488 bulletins, 3 576 lignes bulletin
# Prérequis : step1 + step2 exécutés

import random
import datetime
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, timedelta

from django.utils import timezone
from django.contrib.auth.hashers import make_password

from apps.accounts.models import User, Membership
from apps.schools.models import (
    School, SchoolGroup, SchoolYear, Period,
    SchoolClass, Subject, ClassSubject,
    Note, Bulletin, BulletinLine, BulletinConfig,
)
from apps.students.models import Student, StudentGuardian
from apps.payments.models import Payment
from apps.teachers.models import Attendance

random.seed(123)
NOW = timezone.now()
UTC = datetime.timezone.utc

# ── PARTIE A
groupe_mande = SchoolGroup.objects.get(id=1)
sankara = School.objects.create(
    name='Lycée Privé Excellence Sankara',
    city='Bamako', address='ACI 2000', country='Mali',
    accounting_enabled=True, group=groupe_mande,
)
print(f'✓ École : {sankara.name} (id={sankara.id})')

kadiatou = User.objects.create_user(
    phone_number='76000003', password='test123',
    full_name='Kadiatou Sanogo', role='director', is_active=True,
)
Membership.objects.create(
    user=kadiatou, school=sankara,
    role='director', job_title='Directrice', is_default=True,
)
print(f'✓ Directrice : {kadiatou.full_name}')

# ── PARTIE B
annee = SchoolYear.objects.create(
    school=sankara, name='2025-2026',
    start_date=date(2025,10,1), end_date=date(2026,6,27), is_active=True,
)
PERIODES_DEF = [
    ('Trimestre 1',1,date(2025,10,1),date(2025,12,20),False),
    ('Trimestre 2',2,date(2026,1,5), date(2026,3,28), False),
    ('Trimestre 3',3,date(2026,4,6), date(2026,6,27), True),
]
periodes = []
for name,order,sd,ed,notes_open in PERIODES_DEF:
    periodes.append(Period.objects.create(
        school_year=annee, name=name, order=order,
        period_type='trimester', start_date=sd, end_date=ed,
        is_notes_open=notes_open,
    ))
print(f'✓ Année {annee.name} + {len(periodes)} trimestres')

# ── PARTIE C
TEACHERS_DEF = [
    ('76000016','Issa Konaré'),('76000017','Daouda Bamba'),
    ('76000018','Assitan Touré'),('76000019','Mamadou Cissé'),
    ('76000020','Rokia Fofana'),
]
teacher_users = []
for phone,name in TEACHERS_DEF:
    u = User.objects.create_user(
        phone_number=phone, password='test123',
        full_name=name, role='teacher', is_active=True,
    )
    Membership.objects.create(
        user=u, school=sankara, role='teacher',
        job_title='Enseignant(e)', is_default=True,
    )
    teacher_users.append(u)
t_issa,t_daouda,t_assitan,t_mamadou,t_rokia = teacher_users
print(f'✓ {len(teacher_users)} enseignants créés')

SUBJECT_DEFS = [
    ('Français','FR','#6366f1'),('Mathématiques','MATH','#2563EB'),
    ('Physique-Chimie','PC','#7C3AED'),('Sciences naturelles','SVT','#059669'),
    ('Histoire-Géographie','HG','#D97706'),('Anglais','ANG','#DC2626'),
    ('Éducation civique','EC','#0891b2'),('Sport','EPS','#16a34a'),
    ('Philosophie','PHILO','#9333ea'),('Économie-Gestion','ECO-G','#b45309'),
    ('Économie','ECO','#ca8a04'),('Comptabilité','COMPTA','#92400e'),
    ('Chimie','CHIMIE','#be185d'),('Arabe','ARABE','#0f766e'),
]
subjects = {}
for name,short,color in SUBJECT_DEFS:
    subjects[name] = Subject.objects.create(
        school=sankara, name=name, short_name=short, color=color
    )
print(f'✓ {len(subjects)} matières créées')

TEACHER_MAP = {
    'Français':t_issa,'Philosophie':t_issa,
    'Mathématiques':t_daouda,'Physique-Chimie':t_daouda,
    'Sciences naturelles':t_assitan,'Chimie':t_assitan,
    'Histoire-Géographie':t_mamadou,'Économie':t_mamadou,
    'Économie-Gestion':t_mamadou,'Comptabilité':t_mamadou,
    'Anglais':t_rokia,'Arabe':t_rokia,
    'Éducation civique':t_rokia,'Sport':t_rokia,
}

CLASSES_DEF = [
    ('10ème Année',45,100_000,(2008,2009),[
        ('Français',4),('Mathématiques',4),('Physique-Chimie',3),
        ('Sciences naturelles',3),('Histoire-Géographie',2),
        ('Anglais',3),('Éducation civique',1),('Sport',1)]),
    ('11ème Sciences',35,120_000,(2007,2008),[
        ('Français',3),('Mathématiques',4),('Physique-Chimie',4),
        ('Sciences naturelles',4),('Histoire-Géographie',2),
        ('Anglais',2),('Éducation civique',1),('Sport',1)]),
    ('11ème Économie',32,110_000,(2007,2008),[
        ('Français',3),('Mathématiques',3),('Économie-Gestion',4),
        ('Histoire-Géographie',3),('Anglais',3),
        ('Éducation civique',1),('Sport',1)]),
    ('11ème Lettres',28,100_000,(2007,2008),[
        ('Français',4),('Philosophie',3),('Histoire-Géographie',3),
        ('Anglais',3),('Arabe',2),('Éducation civique',1),('Sport',1)]),
    ('Terminale TSS',30,130_000,(2006,2007),[
        ('Français',3),('Philosophie',4),('Histoire-Géographie',4),
        ('Économie',3),('Anglais',2),('Éducation civique',1),('Sport',1)]),
    ('Terminale TSECO',27,120_000,(2006,2007),[
        ('Français',3),('Mathématiques',3),('Économie-Gestion',4),
        ('Comptabilité',4),('Anglais',2),('Éducation civique',1),('Sport',1)]),
    ('Terminale Exactes',25,130_000,(2006,2007),[
        ('Français',3),('Mathématiques',5),('Physique-Chimie',5),
        ('Sciences naturelles',4),('Anglais',2),
        ('Éducation civique',1),('Sport',1)]),
    ('Terminale Expérimentales',22,130_000,(2006,2007),[
        ('Français',3),('Sciences naturelles',5),('Physique-Chimie',4),
        ('Chimie',4),('Anglais',2),('Éducation civique',1),('Sport',1)]),
]

classes_meta = []
cs_by_class  = defaultdict(list)
for cname,csize,fee,dob_years,subj_list in CLASSES_DEF:
    klass = SchoolClass.objects.create(
        school=sankara, name=cname, level='secondaire_gen',
        annual_fee=fee, max_capacity=csize, is_active=True,
    )
    classes_meta.append((klass,csize,fee,dob_years))
    for i,(sname,coeff) in enumerate(subj_list,1):
        cs = ClassSubject.objects.create(
            school_class=klass, subject=subjects[sname],
            coefficient=Decimal(str(coeff)),
            note_system='moyenne_simple',
            teacher=TEACHER_MAP[sname], order=i, is_active=True,
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

def random_dob(y1,y2):
    s = date(y1,1,1)
    return s + timedelta(days=random.randint(0,(date(y2,12,31)-s).days))

sankara_codes = [str(c) for c in random.sample(range(100000,1000000), 244)]
code_idx = 0
student_objs = []

for klass,csize,fee,dob_years in classes_meta:
    for _ in range(csize):
        prenom = random.choice(PRENOMS_M if random.random()<0.55 else PRENOMS_F)
        s = Student(
            school=sankara, school_class=klass,
            full_name=f'{prenom} {random.choice(NOMS)}',
            date_of_birth=random_dob(*dob_years),
            tuition_fee=fee, access_code=sankara_codes[code_idx], is_active=True,
        )
        code_idx += 1
        student_objs.append(s)

students_list = Student.objects.bulk_create(student_objs, batch_size=200)
print(f'✓ {len(students_list)} élèves créés')

enroll_base = datetime.datetime(2025,10,1,tzinfo=UTC)
for s in students_list:
    s.enrolled_at = enroll_base + timedelta(days=random.randint(0,19))
Student.objects.bulk_update(students_list, ['enrolled_at'], batch_size=200)

students_by_class = defaultdict(list)
for s in students_list:
    students_by_class[s.school_class_id].append(s)

parent_hashed_pwd = make_password('test123')
parent_objs = []
guardian_links = []
parent_pool = []

for s in students_list:
    reuse = (len(parent_pool)>0 and random.random()<0.15)
    if reuse:
        pidx = random.choice(parent_pool)
        guardian_links.append((s,pidx,random.choice(['father','mother','guardian'])))
    else:
        prenom_p = random.choice(PRENOMS_P_M if random.random()<0.50 else PRENOMS_P_F)
        phone_p = f'6{random.randint(0,9)}{random.randint(100000,999999)}'
        parent_objs.append(User(
            phone_number=phone_p, password=parent_hashed_pwd,
            full_name=f'{prenom_p} {random.choice(NOMS)}',
            role='parent', is_active=True,
        ))
        new_idx = len(parent_objs)-1
        parent_pool.append(new_idx)
        guardian_links.append((s,new_idx,random.choice(['father','mother'])))

created_parents = User.objects.bulk_create(parent_objs, batch_size=200)
print(f'✓ {len(created_parents)} parents créés')

sg_objs = []
seen_pairs = set()
for student,pidx,rel in guardian_links:
    parent = created_parents[pidx]
    pair = (parent.id,student.id)
    if pair in seen_pairs: continue
    seen_pairs.add(pair)
    sg_objs.append(StudentGuardian(
        guardian=parent, student=student, relationship=rel, is_primary=True,
    ))
StudentGuardian.objects.bulk_create(sg_objs, batch_size=200)
print(f'✓ {len(sg_objs)} liens parent-élève créés')

lyc_2025_seq = 1; lyc_2026_seq = 1
payment_objs = []
v1_s,v1_e = date(2025,10,1),date(2025,10,31)
v2_s,v2_e = date(2026,1,5), date(2026,2,15)

def rand_date(s,e):
    return s + timedelta(days=random.randint(0,(e-s).days))

for s in students_list:
    fee=int(s.tuition_fee); v=fee//2; v2=fee-v
    r=random.random()
    if r<0.65:
        payment_objs.append(Payment(student=s,amount=v,
            receipt_number=f'LYC-2025-{lyc_2025_seq:04d}',
            collected_by=kadiatou,payment_date=rand_date(v1_s,v1_e),is_cancelled=False))
        lyc_2025_seq+=1
        payment_objs.append(Payment(student=s,amount=v2,
            receipt_number=f'LYC-2026-{lyc_2026_seq:04d}',
            collected_by=kadiatou,payment_date=rand_date(v2_s,v2_e),is_cancelled=False))
        lyc_2026_seq+=1
    elif r<0.85:
        payment_objs.append(Payment(student=s,amount=v,
            receipt_number=f'LYC-2025-{lyc_2025_seq:04d}',
            collected_by=kadiatou,payment_date=rand_date(v1_s,v1_e),is_cancelled=False))
        lyc_2025_seq+=1

Payment.objects.bulk_create(payment_objs, batch_size=500)
total_paid = sum(int(p.amount) for p in payment_objs)
print(f'✓ {len(payment_objs)} paiements créés ({total_paid:,} FCFA)')

# ── PARTIE E — Absences
def weekdays_between(s,e):
    d,days=s,[]
    while d<=e:
        if d.weekday()<5: days.append(d)
        d+=timedelta(days=1)
    return days

abs_pool = (weekdays_between(date(2025,10,1),date(2025,12,20)) +
            weekdays_between(date(2026,1,5), date(2026,3,28)))

absence_objs = []
for s in students_list:
    for d in random.sample(abs_pool, random.randint(8,12)):
        status = 'absent' if random.random()<0.70 else 'late'
        absence_objs.append(Attendance(
            school=sankara, school_class=s.school_class, student=s,
            teacher=kadiatou, date=d, status=status,
            note='', recorded_at=NOW, updated_at=NOW,
        ))

Attendance.objects.bulk_create(absence_objs, batch_size=1000, ignore_conflicts=True)
print(f'✓ {len(absence_objs)} absences créées')

# ── PARTIE F — Notes + Bulletins
BulletinConfig.objects.get_or_create(school=sankara, defaults={
    'republic_line1':'REPUBLIQUE DU MALI',
    'republic_line2':'UN PEUPLE - UN BUT - UNE FOI',
    'ministry_line1':"MINISTERE DE L'EDUCATION NATIONALE",
    'bulletin_title':'RELEVE DE NOTES',
    'footer_left':'Le Parent / Tuteur','footer_right':'La Directrice',
})

n = len(students_list)
profile_pool = (
    [('excellent',15.0,20.0)]*int(0.20*n) +
    [('passable', 10.0,14.5)]*int(0.55*n) +
    [('faible',    5.0, 9.5)]*(n-int(0.20*n)-int(0.55*n))
)
random.shuffle(profile_pool)
base_score = {}
for s,(_, rmin, rmax) in zip(students_list, profile_pool):
    base_score[s.id] = random.uniform(rmin, rmax)

t3_student_ids = set()
for klass,_,_,_ in classes_meta:
    class_students = students_by_class[klass.id]
    n_t3 = max(1, int(0.40*len(class_students)))
    for s in random.sample(class_students, n_t3):
        t3_student_ids.add(s.id)

def gen_note(base):
    return round(max(0.0,min(20.0,base+random.uniform(-1.0,1.0))),1)

def mention(avg):
    if avg>=16: return 'Très bien'
    if avg>=14: return 'Bien'
    if avg>=12: return 'Assez bien'
    if avg>=10: return 'Passable'
    return 'Insuffisant'

all_note_objs=[]; all_bulletin_objs=[]; bulletin_map={}
class_period_avgs=defaultdict(list); cs_period_avgs=defaultdict(list)

for period in periodes:
    is_t3=(period.order==3)
    for klass,_,_,_ in classes_meta:
        cs_list=cs_by_class[klass.id]
        class_students=students_by_class[klass.id]
        if not cs_list: continue
        total_coeff=sum(cs.coefficient for cs in cs_list) or Decimal('1')

        for student in class_students:
            if is_t3 and student.id not in t3_student_ids: continue
            base=base_score[student.id]; wsum=Decimal('0'); blines=[]

            for cs in cs_list:
                dev_val=gen_note(base); comp_val=gen_note(base)
                all_note_objs.append(Note(
                    student=student,class_subject=cs,period=period,
                    note_type='devoir',position=1,value=Decimal(str(dev_val)),
                    entered_by=cs.teacher or kadiatou,entered_at=NOW,modified_at=NOW))
                all_note_objs.append(Note(
                    student=student,class_subject=cs,period=period,
                    note_type='composition',position=2,value=Decimal(str(comp_val)),
                    entered_by=cs.teacher or kadiatou,entered_at=NOW,modified_at=NOW))
                final_avg=Decimal(str(round((dev_val+comp_val)/2,2)))
                weighted=(final_avg*cs.coefficient).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)
                wsum+=weighted
                blines.append({'cs':cs,'dev':Decimal(str(dev_val)),'comp':Decimal(str(comp_val)),
                    'final':final_avg,'weighted':weighted,'mention':mention(float(final_avg)),'rank_subj':None})
                if not is_t3:
                    cs_period_avgs[(cs.id,period.id)].append((student.id,float(final_avg)))

            general_avg=(wsum/total_coeff).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)
            if not is_t3:
                b=Bulletin(student=student,period=period,school_class=klass,
                    generated_at=NOW,generated_by=kadiatou,
                    is_published=True,published_at=NOW,
                    general_average=general_avg,appreciation=mention(float(general_avg)),is_cancelled=False)
                all_bulletin_objs.append(b)
                bulletin_map[(student.id,period.id)]={'bobj':b,'lines':blines}
                class_period_avgs[(klass.id,period.id)].append((student.id,float(general_avg)))

for (cs_id,period_id),avgs in cs_period_avgs.items():
    sorted_avgs=sorted(avgs,key=lambda x:x[1],reverse=True)
    rank_map={sid:r+1 for r,(sid,_) in enumerate(sorted_avgs)}
    for (sid,pid),bdata in bulletin_map.items():
        if pid!=period_id: continue
        for line in bdata['lines']:
            if line['cs'].id==cs_id: line['rank_subj']=rank_map.get(sid)

Note.objects.bulk_create(all_note_objs, batch_size=2000)
print(f'✓ {len(all_note_objs)} notes créées')

created_bulletins=Bulletin.objects.bulk_create(all_bulletin_objs,batch_size=500)

for (class_id,period_id),avgs in class_period_avgs.items():
    sorted_avgs=sorted(avgs,key=lambda x:x[1],reverse=True)
    first_avg=Decimal(str(round(sorted_avgs[0][1],2))) if sorted_avgs else None
    class_size=len(sorted_avgs)
    rank_map={sid:r+1 for r,(sid,_) in enumerate(sorted_avgs)}
    for (sid,pid),bdata in bulletin_map.items():
        b=bdata['bobj']
        if pid==period_id and b.school_class_id==class_id:
            b.rank=rank_map.get(sid); b.class_size=class_size; b.first_average=first_avg

Bulletin.objects.bulk_update(all_bulletin_objs,['rank','class_size','first_average'],batch_size=500)
print(f'✓ {len(created_bulletins)} bulletins créés (T1+T2)')

all_bline_objs=[]
for b in created_bulletins:
    bdata=bulletin_map.get((b.student_id,b.period_id))
    if not bdata: continue
    for line in bdata['lines']:
        all_bline_objs.append(BulletinLine(
            bulletin=b,class_subject=line['cs'],
            devoir_average=line['dev'],compo_grade=line['comp'],
            final_average=line['final'],weighted_grade=line['weighted'],
            appreciation=line['mention'],rank_in_subject=line['rank_subj']))

BulletinLine.objects.bulk_create(all_bline_objs,batch_size=2000)
print(f'✓ {len(all_bline_objs)} lignes bulletin créées')

notes_t3=sum(1 for n in all_note_objs if n.period_id==periodes[2].id)
notes_t1t2=len(all_note_objs)-notes_t3

print()
print('=' * 62)
print('ÉTAPE 5 — RÉSULTAT  Lycée Privé Excellence Sankara')
print('=' * 62)
print(f'  École (id)               : {sankara.id}')
print(f'  Enseignants              : {len(teacher_users)}')
print(f'  Matières (Subject)       : {len(subjects)}')
print(f'  Classes                  : {len(classes_meta)}')
print(f'  ClassSubjects            : {total_cs}')
print(f'  Élèves                   : {len(students_list)}')
print(f'  Parents                  : {len(created_parents)}')
print(f'  Liens parent-élève       : {len(sg_objs)}')
print(f'  Paiements                : {len(payment_objs)} ({total_paid:,} FCFA)')
print(f'  Absences (T1+T2)         : {len(absence_objs)}')
print(f'  Notes T1+T2 (tous)       : {notes_t1t2:,}')
print(f'  Notes T3 (≈40%/classe)   : {notes_t3:,}')
print(f'  Bulletins T1+T2 publiés  : {len(created_bulletins)}')
print(f'  Lignes bulletin          : {len(all_bline_objs)}')
print(f'  BulletinConfig           : 1')
print('=' * 62)
