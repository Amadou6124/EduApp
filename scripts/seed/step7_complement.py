# ÉTAPE 7 — Données complémentaires Sundiata Keïta + Sankara
# Exécuter : python manage.py shell < scripts/seed/step7_complement.py
#
# random.seed(789) — reproductible
# PARTIE 1 : StudentObservation (comportement, académique, santé)
# PARTIE 2 : QuickAssessment (élèves avg<10)
# PARTIE 3 : EmployeeProfile + SalaryPayment + ExpenseCategory + Expense
# PARTIE 4 : SchoolAnnouncement
# Crée : ~255 obs., ~514 QA, 11 EmpProfile, 84 salaires, 12 catégories,
#        ~74 dépenses, 5 annonces
# Prérequis : step1-step6 exécutés

import random, datetime, calendar
from decimal import Decimal
from datetime import date, timedelta
from collections import defaultdict

from django.utils import timezone

from apps.accounts.models import User, Membership
from apps.schools.models import (
    School, SchoolClass, ClassSubject, Period, Bulletin, SchoolAnnouncement
)
from apps.students.models import Student
from apps.teachers.models import StudentObservation, QuickAssessment
from apps.accounting.models import (
    EmployeeProfile, SalaryPayment, Expense, ExpenseCategory
)

random.seed(789)
NOW = timezone.now()
UTC = datetime.timezone.utc

sundiata = School.objects.get(id=1)
sankara  = School.objects.get(id=4)
ibrahim  = Membership.objects.get(school=sundiata, role='director').user
kadiatou = Membership.objects.get(school=sankara,  role='director').user

def rand_dt_in(period):
    delta = (period.end_date - period.start_date).days
    d = period.start_date + timedelta(days=random.randint(0, delta))
    return datetime.datetime(d.year, d.month, d.day,
                             random.randint(8, 16), random.randint(0, 59), tzinfo=UTC)

def rand_d_in(period):
    delta = (period.end_date - period.start_date).days
    return period.start_date + timedelta(days=random.randint(0, delta))

sundiata_periods = list(Period.objects.filter(
    school_year__school=sundiata).order_by('order'))
sankara_t1t2 = list(Period.objects.filter(
    school_year__school=sankara, order__lte=2).order_by('order'))

students_by_class   = defaultdict(list)
class_teacher_users = defaultdict(list)
cs_by_class         = defaultdict(list)

for s in Student.objects.filter(school__in=[sundiata, sankara]).select_related('school_class'):
    students_by_class[(s.school_id, s.school_class_id)].append(s)

for cs in (ClassSubject.objects
           .filter(school_class__school__in=[sundiata, sankara])
           .select_related('teacher', 'school_class')):
    key = (cs.school_class.school_id, cs.school_class_id)
    cs_by_class[key].append(cs)
    if cs.teacher and cs.teacher not in class_teacher_users[key]:
        class_teacher_users[key].append(cs.teacher)

# ═══════════════════════════════════════════════════════════════════════════
# PARTIE 1 — Observations
# ═══════════════════════════════════════════════════════════════════════════
CONTENT_POOL = {
    'behaviour': [
        "L'élève perturbe régulièrement le cours avec des bavardages. Des mesures s'imposent.",
        "Comportement exemplaire ce trimestre, très respectueux de ses camarades et du personnel.",
        "Tendance à l'agitation et aux distractions en classe. Un entretien avec les parents est souhaitable.",
        "Difficultés à respecter les consignes de classe malgré les rappels répétés.",
        "Attitude très positive, encourage ses camarades dans leur travail. Excellent esprit d'équipe.",
        "Retards répétés en début de séance. À régulariser impérativement.",
        "L'élève montre de l'agressivité envers certains camarades. Suivi éducatif recommandé.",
        "Très bonne intégration dans la classe, leader positif apprécié de tous.",
    ],
    'academic': [
        "Des lacunes importantes notées ce trimestre. Un soutien scolaire est vivement recommandé.",
        "Bonne progression dans les matières principales. À encourager à fournir encore plus d'efforts.",
        "Les devoirs ne sont pas rendus régulièrement. Un suivi parental est nécessaire à la maison.",
        "Niveau général satisfaisant pour la période. Continue à travailler sérieusement.",
        "Résultats en baisse par rapport au trimestre précédent. Doit redoubler d'efforts.",
        "Participation active et très engagée en classe. Très bon niveau académique global.",
        "Difficultés persistantes en expression écrite. Orientation vers le soutien conseillée.",
        "Travail sérieux et régulier. Les efforts fournis se reflètent positivement dans les résultats.",
        "L'élève ne manifeste pas suffisamment d'intérêt pour les matières enseignées ce trimestre.",
    ],
    'health': [
        "Plusieurs absences pour raison de santé ce trimestre. Un certificat médical a été fourni.",
        "L'élève présente des signes de fatigue persistante. Un suivi médical est vivement conseillé.",
        "Absence prolongée signalée. Les parents ont informé l'administration de la situation médicale.",
        "Difficultés de concentration probablement liées à un état de santé fragile.",
        "L'élève a été envoyé à l'infirmerie ce mois-ci. Les parents ont été immédiatement prévenus.",
    ],
}

PARENT_MSGS = [
    "Cher parent/tuteur, votre enfant rencontre des difficultés ce trimestre. Un rendez-vous avec l'enseignant peut être organisé sur simple demande auprès de la direction.",
    "Bonjour cher parent, votre enfant fait de bons progrès ce trimestre. Continuez à l'encourager et à l'accompagner dans son travail à la maison.",
    "Cher parent/tuteur, votre enfant a été absent à plusieurs reprises ce trimestre. Merci de prendre contact avec l'administration pour régulariser la situation.",
    "Cher parent, le comportement de votre enfant en classe nécessite votre attention. Nous vous invitons à nous contacter afin d'en discuter ensemble.",
    "Bonjour cher parent, votre enfant travaille sérieusement et s'intègre très bien dans la classe. Continuez à le soutenir dans ses efforts quotidiens.",
]

obs_objs = []

def gen_observations(school, classes, periods, n_min, n_max):
    for klass in classes:
        s_pool = students_by_class.get((school.id, klass.id), [])
        t_pool = class_teacher_users.get((school.id, klass.id), [])
        if not s_pool or not t_pool:
            continue
        n_obs_students = max(1, int(0.15 * len(s_pool)))
        observed = random.sample(s_pool, min(n_obs_students, len(s_pool)))
        for period in periods:
            n_obs = random.randint(n_min, n_max)
            for _ in range(n_obs):
                student  = random.choice(observed)
                teacher  = random.choice(t_pool)
                obs_type = random.choice(['behaviour', 'academic', 'health'])
                is_priv  = random.random() < 0.30
                is_vis   = (not is_priv) and (random.random() < 0.30)
                obs_objs.append(StudentObservation(
                    school=school, student=student, teacher=teacher,
                    observation_type=obs_type,
                    content=random.choice(CONTENT_POOL[obs_type]),
                    is_private=is_priv,
                    is_visible_to_parent=is_vis,
                    parent_message=random.choice(PARENT_MSGS) if is_vis else '',
                    is_read=False,
                    created_at=rand_dt_in(period),
                ))

gen_observations(sundiata, list(SchoolClass.objects.filter(school=sundiata)), sundiata_periods, 3, 5)
gen_observations(sankara,  list(SchoolClass.objects.filter(school=sankara)),  sankara_t1t2,    2, 3)

StudentObservation.objects.bulk_create(obs_objs, batch_size=500)
n_priv = sum(1 for o in obs_objs if o.is_private)
n_vis  = sum(1 for o in obs_objs if o.is_visible_to_parent)
print(f'✓ P1 : {len(obs_objs)} observations (privées={n_priv} | visibles parents={n_vis})')

# ═══════════════════════════════════════════════════════════════════════════
# PARTIE 2 — QuickAssessments
# ═══════════════════════════════════════════════════════════════════════════
struggling = defaultdict(list)
for b in (Bulletin.objects
          .filter(school_class__school__in=[sundiata, sankara],
                  general_average__lt=Decimal('10'))
          .select_related('student', 'period', 'school_class__school')):
    struggling[(b.school_class.school_id, b.period_id)].append(b)

qa_objs = []
for (school_id, period_id), bulletins in struggling.items():
    period = Period.objects.get(id=period_id)
    for b in bulletins:
        cs_list = cs_by_class.get((school_id, b.school_class_id), [])
        if not cs_list:
            continue
        cs    = random.choice(cs_list)
        value = Decimal(str(round(random.uniform(0.5, 8.5), 1)))
        qa_objs.append(QuickAssessment(
            teacher=cs.teacher,
            student=b.student,
            class_subject=cs,
            period=period,
            assessment_type=random.choice(['oral', 'written']),
            value=value,
            max_value=Decimal('10'),
            note='',
            assessed_at=rand_d_in(period),
            created_at=rand_dt_in(period),
        ))

QuickAssessment.objects.bulk_create(qa_objs, batch_size=1000)
print(f'✓ P2 : {len(qa_objs)} QuickAssessments (élèves avg<10)')

# ═══════════════════════════════════════════════════════════════════════════
# PARTIE 3 — Comptabilité
# ═══════════════════════════════════════════════════════════════════════════
sun_memberships = list(Membership.objects.filter(school=sundiata, role='teacher').select_related('user'))
lyc_memberships = list(Membership.objects.filter(school=sankara,  role='teacher').select_related('user'))

ep_objs = (
    [EmployeeProfile(membership=m, employment_type='permanent',
                     monthly_salary=Decimal('150000'),
                     hire_date=date(2025,10,1), is_active=True,
                     created_at=NOW, updated_at=NOW)
     for m in sun_memberships]
    +
    [EmployeeProfile(membership=m, employment_type='permanent',
                     monthly_salary=Decimal('200000'),
                     hire_date=date(2025,10,1), is_active=True,
                     created_at=NOW, updated_at=NOW)
     for m in lyc_memberships]
)
EmployeeProfile.objects.bulk_create(ep_objs)
print(f'✓ P3a: {len(ep_objs)} EmployeeProfiles (Sundiata×150k | Sankara×200k FCFA/mois)')

SUNDIATA_MONTHS = [(2025,10),(2025,11),(2025,12),(2026,1),(2026,2),(2026,3),(2026,4),(2026,5),(2026,6)]
SANKARA_MONTHS  = [(2025,10),(2025,11),(2025,12),(2026,1),(2026,2),(2026,3)]

def paid_at_dt(year, month):
    last = calendar.monthrange(year, month)[1]
    day  = random.randint(28, last)
    return datetime.datetime(year, month, day, random.randint(8,11), 0, tzinfo=UTC)

sal_objs = []
for m in sun_memberships:
    for year, month in SUNDIATA_MONTHS:
        sal_objs.append(SalaryPayment(
            employee=m, school=sundiata,
            year=year, month=month,
            amount=Decimal('150000'),
            status='paid', payment_method='cash',
            paid_at=paid_at_dt(year, month),
            paid_by=ibrahim,
            employee_name=m.user.full_name,
            is_cancelled=False, created_at=NOW,
        ))
for m in lyc_memberships:
    for year, month in SANKARA_MONTHS:
        sal_objs.append(SalaryPayment(
            employee=m, school=sankara,
            year=year, month=month,
            amount=Decimal('200000'),
            status='paid', payment_method='cash',
            paid_at=paid_at_dt(year, month),
            paid_by=kadiatou,
            employee_name=m.user.full_name,
            is_cancelled=False, created_at=NOW,
        ))

SalaryPayment.objects.bulk_create(sal_objs, batch_size=500)
total_sal = sum(int(s.amount) for s in sal_objs)
total_sal_sun = sum(int(s.amount) for s in sal_objs if s.school_id==sundiata.id)
total_sal_lyc = sum(int(s.amount) for s in sal_objs if s.school_id==sankara.id)
print(f'✓ P3b: {len(sal_objs)} SalaryPayments — {total_sal_sun:,}+{total_sal_lyc:,} = {total_sal:,} FCFA')

EXPENSE_CAT_DEF = [
    ('Électricité','zap'),('Eau','droplets'),
    ('Fournitures scolaires','package'),('Entretien','wrench'),
    ('Transport','truck'),('Autres','more-horizontal'),
]
cat_sun_objs = [ExpenseCategory(school=sundiata, name=n, icon=i, is_active=True, created_at=NOW)
                for n,i in EXPENSE_CAT_DEF]
cat_lyc_objs = [ExpenseCategory(school=sankara,  name=n, icon=i, is_active=True, created_at=NOW)
                for n,i in EXPENSE_CAT_DEF]
ExpenseCategory.objects.bulk_create(cat_sun_objs + cat_lyc_objs)
cats_sun = {c.name: c for c in cat_sun_objs}
cats_lyc = {c.name: c for c in cat_lyc_objs}
print(f'✓ P3c: {len(cat_sun_objs)+len(cat_lyc_objs)} ExpenseCategories')

SUN_RANGES = {
    'Électricité':(45_000,80_000),'Eau':(15_000,30_000),
    'Fournitures scolaires':(20_000,100_000),'Entretien':(10_000,50_000),
    'Transport':(5_000,25_000),'Autres':(5_000,30_000),
}
LYC_RANGES = {
    'Électricité':(60_000,110_000),'Eau':(20_000,40_000),
    'Fournitures scolaires':(30_000,130_000),'Entretien':(15_000,70_000),
    'Transport':(10_000,35_000),'Autres':(10_000,40_000),
}
EXPENSE_DESCS = {
    'Électricité':['Facture EDM du mois','Règlement facture électricité mensuelle'],
    'Eau':['Facture SOMAGEP du mois','Règlement consommation eau mensuelle'],
    'Fournitures scolaires':['Achat fournitures et papeterie','Matériel pédagogique et didactique',
                             'Craies, marqueurs et consommables','Registres, cahiers et fournitures bureau'],
    'Entretien':['Travaux entretien et nettoyage des locaux',
                 'Maintenance et petites réparations bâtiment',
                 "Produits d'entretien et de nettoyage"],
    'Transport':['Frais de déplacement du personnel',
                 'Carburant et frais de transport divers','Transport de matériel scolaire'],
    'Autres':['Frais divers de fonctionnement',
              'Dépenses imprévues et remboursements','Frais administratifs et postaux'],
}

exp_objs = []

def gen_expenses(school, director, cats, ranges, months):
    cat_names = list(cats.keys())
    for year, month in months:
        n_exp = random.randint(4, 6)
        chosen = random.sample(cat_names, min(n_exp, len(cat_names)))
        last_day = calendar.monthrange(year, month)[1]
        for cat_name in chosen:
            rmin, rmax = ranges[cat_name]
            amount  = round(random.randint(rmin, rmax) / 500) * 500
            exp_day = random.randint(1, last_day)
            desc    = random.choice(EXPENSE_DESCS[cat_name])
            exp_objs.append(Expense(
                school=school, category=cats[cat_name],
                amount=Decimal(str(amount)),
                date=date(year, month, exp_day),
                description=f'{desc} ({year}/{month:02d})',
                payment_method='cash', paid_by=director,
                is_cancelled=False, created_at=NOW,
            ))

gen_expenses(sundiata, ibrahim,   cats_sun, SUN_RANGES, SUNDIATA_MONTHS)
gen_expenses(sankara,  kadiatou,  cats_lyc, LYC_RANGES, SANKARA_MONTHS)
Expense.objects.bulk_create(exp_objs, batch_size=500)
total_dep = sum(int(e.amount) for e in exp_objs)
total_dep_sun = sum(int(e.amount) for e in exp_objs if e.school_id==sundiata.id)
total_dep_lyc = sum(int(e.amount) for e in exp_objs if e.school_id==sankara.id)
print(f'✓ P3d: {len(exp_objs)} dépenses — {total_dep_sun:,}+{total_dep_lyc:,} = {total_dep:,} FCFA')

# ═══════════════════════════════════════════════════════════════════════════
# PARTIE 4 — Annonces
# ═══════════════════════════════════════════════════════════════════════════
ANNOUNCEMENTS = [
    (sundiata, ibrahim,
     "Réunion parents-professeurs — Trimestre 1",
     "Chers parents et tuteurs,\n\nNous avons le plaisir de vous informer qu'une réunion parents-professeurs "
     "se tiendra le samedi 22 novembre 2025 à partir de 9h dans les locaux de l'école.\n\n"
     "Cette réunion est l'occasion d'échanger avec les enseignants sur les résultats "
     "et le comportement de vos enfants au premier trimestre.\n\nVotre présence est vivement souhaitée.\n\nLa Direction",
     datetime.datetime(2025,11,8,10,0,tzinfo=UTC)),

    (sundiata, ibrahim,
     "Résultats du Trimestre 2 disponibles",
     "Chers parents et tuteurs,\n\nLes bulletins du deuxième trimestre sont désormais disponibles sur l'application EduApp.\n\n"
     "Vous pouvez consulter les résultats de votre enfant en vous connectant avec votre code d'accès habituel. "
     "Pour toute question, n'hésitez pas à contacter l'administration.\n\nLa Direction",
     datetime.datetime(2026,4,7,9,0,tzinfo=UTC)),

    (sundiata, ibrahim,
     "Fête de fin d'année scolaire 2025-2026",
     "Chers parents, élèves et membres du personnel,\n\nNous avons le plaisir de vous annoncer que la fête de fin "
     "d'année scolaire 2025-2026 se tiendra le vendredi 26 juin 2026 à partir de 14h dans la cour de l'école.\n\n"
     "Au programme : remise des prix d'excellence, prestations culturelles des élèves "
     "et moment convivial entre toute la communauté éducative.\n\nVotre présence nous fera honneur.\n\nLa Direction",
     datetime.datetime(2026,6,12,8,30,tzinfo=UTC)),

    (sankara, kadiatou,
     "Calendrier des examens du Bac blanc",
     "Chers élèves et chers parents,\n\nLe calendrier des examens du Bac blanc est maintenant disponible. "
     "Les épreuves se dérouleront du 09 au 14 mars 2026 selon le planning affiché dans les classes.\n\n"
     "Nous rappelons à tous les candidats l'importance de bien se préparer à ces examens "
     "qui constituent une répétition grandeur nature du Baccalauréat National.\n\nBon courage.\n\nLa Direction",
     datetime.datetime(2026,2,3,11,0,tzinfo=UTC)),

    (sankara, kadiatou,
     "Ouverture des inscriptions pour le Trimestre 3",
     "Chers parents et tuteurs,\n\nNous vous informons que les inscriptions pour le troisième trimestre sont "
     "officiellement ouvertes à compter du 6 avril 2026.\n\n"
     "Les frais de scolarité restants doivent être réglés auprès du bureau de la scolarité avant le 20 avril 2026. "
     "Pour tout renseignement, veuillez contacter l'administration du Lycée Privé Excellence Sankara.\n\nLa Direction",
     datetime.datetime(2026,4,1,9,0,tzinfo=UTC)),
]

ann_objs = []
for school, author, title, body, pub_at in ANNOUNCEMENTS:
    ann_objs.append(SchoolAnnouncement(
        school=school, author=author,
        title=title, body=body, audience='school',
        is_published=True, published_at=pub_at,
        created_at=pub_at, updated_at=pub_at,
    ))

SchoolAnnouncement.objects.bulk_create(ann_objs)
print(f'✓ P4 : {len(ann_objs)} annonces (Sundiata 3 | Sankara 2)')

# ═══════════════════════════════════════════════════════════════════════════
# RÉCAPITULATIF
# ═══════════════════════════════════════════════════════════════════════════
print()
print('=' * 66)
print('ÉTAPE 7 — RÉSULTAT')
print('=' * 66)
print(f'  P1 Observations                : {len(obs_objs)}')
print(f'     dont privées (≈30%)         : {n_priv}')
print(f'     dont visibles parents (≈21%): {n_vis}')
print(f'  P2 QuickAssessments (avg<10)   : {len(qa_objs)}')
print(f'  P3 EmployeeProfiles            : {len(ep_objs)} '
      f'(Sundiata {len(sun_memberships)} | Sankara {len(lyc_memberships)})')
print(f'     SalaryPayments              : {len(sal_objs)} — {total_sal:,} FCFA')
print(f'       Sundiata 6×9 mois         : {total_sal_sun:,} FCFA')
print(f'       Sankara  5×6 mois         : {total_sal_lyc:,} FCFA')
print(f'     ExpenseCategories           : {len(cat_sun_objs)+len(cat_lyc_objs)} (6+6)')
print(f'     Dépenses                    : {len(exp_objs)} — {total_dep:,} FCFA')
print(f'       Sundiata (9 mois)         : {total_dep_sun:,} FCFA')
print(f'       Sankara  (6 mois)         : {total_dep_lyc:,} FCFA')
print(f'  P4 Annonces publiées           : {len(ann_objs)} (Sundiata 3 | Sankara 2)')
print('=' * 66)
