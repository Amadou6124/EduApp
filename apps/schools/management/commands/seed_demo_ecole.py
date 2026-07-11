"""seed_demo_ecole — construit l'ÉCOLE DE DÉMONSTRATION complète, en une commande.

Usage (sur une base FRAÎCHE de préférence) :
    python manage.py flush --noinput
    python manage.py migrate
    python manage.py seed_demo_ecole

Construit « Groupe Scolaire Kalanso » (kalanso = « école » en bambara) :
  • année scolaire (dynamique autour d'aujourd'hui) + 3 compositions (T1/T2 fermés
    avec bulletins PUBLIÉS, T3 ouvert avec notes provisoires)
  • directeur + 2 enseignants + 3 parents (memberships + identifiants imprimés)
  • 3 classes fondamental_1 ; la classe VITRINE (1ère Année A) est peuplée de
    24 élèves (vrais noms maliens, matricules, codes portail, inscriptions)
  • matières + coefficients + emploi du temps réel (créneaux + récréation)
  • notes T1/T2 (devoir+compo) → bulletins calculés, rangs, publiés ; T3 partiel
  • évaluations formatives publiées aux parents ; quelques absences
  • les 3 leçons v2 (contenu IA payé) rechargées depuis fixtures/demo_lessons_v2.json
    et déployées → parcours élève complet
  • progression réaliste pour 3 élèves « vedettes » (concepts finis, révisions
    mûres/futures, cahier fait, histoire jouée) → les 4 chantiers sont démontrables
  • enchaîne seed_demo_finance + seed_demo_school_life (fiches, paiements,
    émargement, annonces)

Déterministe (random seedé) : deux exécutions sur base fraîche donnent la même école.
"""
import json
import random
from datetime import date, time, timedelta
from decimal import Decimal
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Membership, User, UserRole
from apps.lessons.models import (
    Lesson, LessonContentVersion, LessonDeployment, LessonStatus, Unit,
)
from apps.schools.models import (
    ClassSubject, CourseSlot, EducationLevel, FormativeEvaluation,
    FormativeGrade, Note, NoteType, Period, PeriodType, Bulletin, BulletinLine,
    School, SchoolBreak, SchoolClass, SchoolYear, Subject,
)
from apps.students.models import Student, StudentGuardian
from apps.students.services import ensure_active_enrollment
from apps.student_learning import srs
from apps.student_learning.models import (
    CahierAttempt, ConceptProgress, ConceptReview, QuizAttempt, StoryAttempt,
)
from apps.teachers.models import Attendance

FIXTURE = Path('fixtures/demo_lessons_v2.json')

# 24 élèves — vrais prénoms/noms maliens (mixte)
ELEVES = [
    'Adama Touré', 'Aminata Diallo', 'Moussa Keïta', 'Fatoumata Coulibaly',
    'Ibrahim Traoré', 'Awa Sangaré', 'Sékou Doumbia', 'Mariam Sidibé',
    'Oumar Konaté', 'Kadiatou Dembélé', 'Boubacar Cissé', 'Assétou Diarra',
    'Modibo Camara', 'Ramata Sissoko', 'Youssouf Maïga', 'Djénéba Fofana',
    'Cheick Samaké', 'Hawa Kanté', 'Drissa Ballo', 'Salimata Berthé',
    'Mamadou Sanogo', 'Oumou Guindo', 'Abdoulaye Koné', 'Nana Kouyaté',
]

MATIERES = [
    # (nom, coefficient, max_grade)
    ('Français', 3, 20), ('Mathématiques', 3, 20),
    ('Sciences d\'observation', 2, 20), ('Histoire-Géographie', 2, 20),
    ('Éducation civique et morale', 1, 20),
]


class Command(BaseCommand):
    help = "Construit l'école de démonstration complète (Groupe Scolaire Kalanso)"

    def add_arguments(self, parser):
        parser.add_argument('--seed', type=int, default=42, help='Graine aléatoire')
        parser.add_argument('--skip-annexes', action='store_true',
                            help='Ne pas enchaîner les seeds finance/vie scolaire')

    # ────────────────────────────────────────────────────────────────────
    def handle(self, *args, **opt):
        self.rng = random.Random(opt['seed'])
        with transaction.atomic():
            school = self._school()
            year, periods = self._year_and_periods(school)
            director, profs = self._staff(school)
            classes, demo_class = self._classes(school)
            students = self._students(school, demo_class)
            self._parents(school, students)
            subjects = self._subjects(school, demo_class, profs)
            self._timetable(school, year, subjects)
            self._grades(students, subjects, periods, director, demo_class)
            self._formative(students, subjects, periods, director)
            self._absences(school, demo_class, students, profs)
            lessons = self._lessons(school, demo_class, director, profs)
            self._progression(students, lessons)

        if not opt['skip_annexes']:
            self._annexes(school)

        self._summary(school, director, profs, students)

    # ── briques ──────────────────────────────────────────────────────────
    def _school(self):
        school, _ = School.objects.get_or_create(
            name='Groupe Scolaire Kalanso',
            defaults=dict(short_name='GSK', city='Bamako', country='Mali',
                          school_type='primary', phone_number='+223 20 22 33 44',
                          address='Badalabougou, Rue 132, Bamako'),
        )
        self._ok(f'École : {school.name} (id {school.id})')
        return school

    def _year_and_periods(self, school):
        today = timezone.localdate()
        start_y = today.year if today.month >= 9 else today.year - 1
        year, _ = SchoolYear.objects.get_or_create(
            school=school, name=f'{start_y}-{start_y + 1}',
            defaults=dict(start_date=date(start_y, 10, 1),
                          end_date=date(start_y + 1, 6, 30), is_active=True),
        )
        if not year.is_active:
            year.is_active = True
            year.save(update_fields=['is_active'])

        bounds = [
            ('1ère Composition', date(start_y, 10, 1), date(start_y, 12, 20), False),
            ('2ème Composition', date(start_y + 1, 1, 5), date(start_y + 1, 3, 27), False),
            ('3ème Composition', date(start_y + 1, 3, 30), date(start_y + 1, 6, 30), True),
        ]
        periods = []
        for i, (name, d1, d2, notes_open) in enumerate(bounds, start=1):
            p, _ = Period.objects.get_or_create(
                school_year=year, name=name,
                education_level=EducationLevel.FONDAMENTAL_1,
                defaults=dict(period_type=PeriodType.COMPOSITION, order=i,
                              start_date=d1, end_date=d2, is_notes_open=notes_open),
            )
            periods.append(p)
        self._ok(f'Année {year.name} + {len(periods)} compositions (T3 ouverte)')
        return year, periods

    def _staff(self, school):
        # NB : User.school (champ legacy) est encore lu par les seeds annexes et
        # divers filtres → on le remplit EN PLUS du Membership.
        director, created = User.objects.get_or_create(
            phone_number='70000001',
            defaults=dict(full_name='Sory Ibrahima Kanté', role=UserRole.DIRECTOR,
                          school=school),
        )
        if created:
            director.set_password('demo1234')
            director.save()
        profs = []
        for phone, name in [('70000002', 'Mariam Traoré'), ('70000003', 'Sékou Diarra')]:
            u, created = User.objects.get_or_create(
                phone_number=phone,
                defaults=dict(full_name=name, role=UserRole.TEACHER, school=school),
            )
            if created:
                u.set_password('demo1234')
                u.save()
            profs.append(u)
        # rejouable : recale le legacy User.school ET désarme le changement de mot
        # de passe forcé (sinon le staff démo serait bloqué sur /password/set/ et
        # toutes les sections lazy de l'app se figeraient sur « Chargement… »).
        for u in [director] + profs:
            fields = []
            if u.school_id != school.id:
                u.school = school; fields.append('school')
            if getattr(u, 'must_change_password', False):
                u.must_change_password = False; fields.append('must_change_password')
            if fields:
                u.save(update_fields=fields)
        for u, role in [(director, UserRole.DIRECTOR)] + [(p, UserRole.TEACHER) for p in profs]:
            Membership.objects.get_or_create(user=u, school=school,
                                             defaults=dict(role=role, is_default=True))
        self._ok(f'Staff : directeur + {len(profs)} enseignants (mdp demo1234)')
        return director, profs

    def _classes(self, school):
        specs = [('1ère Année A', 150000), ('2ème Année A', 150000), ('3ème Année A', 165000)]
        classes = []
        for name, fee in specs:
            c, _ = SchoolClass.objects.get_or_create(
                school=school, name=name, is_active=True,
                defaults=dict(level=EducationLevel.FONDAMENTAL_1,
                              annual_fee=Decimal(fee), max_capacity=40),
            )
            classes.append(c)
        self._ok(f'Classes : {", ".join(c.name for c in classes)} (vitrine : {classes[0].name})')
        return classes, classes[0]

    def _students(self, school, demo_class):
        from apps.students.models import generate_matricule, generate_student_access_code
        students = []
        for full_name in ELEVES:
            s = Student.objects.filter(school=school, full_name=full_name).first()
            if s is None:
                parts = full_name.split()
                s = Student.objects.create(
                    school=school, school_class=demo_class, full_name=full_name,
                    first_name=' '.join(parts[:-1]), last_name=parts[-1],
                    matricule=generate_matricule(school),
                    access_code=generate_student_access_code(),
                    tuition_fee=demo_class.annual_fee,
                )
            ensure_active_enrollment(s)
            students.append(s)
        self._ok(f'Élèves : {len(students)} dans {demo_class.name} (matricules + codes portail)')
        return students

    def _parents(self, school, students):
        rels = [('70000010', 'Bakary Touré', 'father'), ('70000011', 'Fanta Diallo', 'mother'),
                ('70000012', 'Sadio Keïta', 'father')]
        for (phone, name, rel), student in zip(rels, students[:3]):
            u, created = User.objects.get_or_create(
                phone_number=phone,
                defaults=dict(full_name=name, role=UserRole.PARENT, school=school))
            if created:
                u.set_password('demo1234')
                u.save()
            Membership.objects.get_or_create(user=u, school=school,
                                             defaults=dict(role=UserRole.PARENT, is_default=True))
            StudentGuardian.objects.get_or_create(
                guardian=u, student=student,
                defaults=dict(full_name=name, phone=phone, relationship=rel, is_primary=True))
        self._ok('Parents : 3 comptes liés (mdp demo1234)')

    def _subjects(self, school, demo_class, profs):
        out = []
        for i, (name, coeff, maxg) in enumerate(MATIERES):
            subj, _ = Subject.objects.get_or_create(school=school, name=name)
            cs, _ = ClassSubject.objects.get_or_create(
                school_class=demo_class, subject=subj,
                defaults=dict(coefficient=Decimal(coeff), max_grade=Decimal(maxg),
                              teacher=profs[i % len(profs)]),
            )
            out.append(cs)
        self._ok(f'Matières : {len(out)} avec coefficients + enseignants')
        return out

    def _timetable(self, school, year, subjects):
        if CourseSlot.objects.filter(school_year=year).exists():
            return
        # Lun→Ven : 2 créneaux le matin, 1 l'après-midi ; récréation 10h-10h30.
        slots = [(time(8, 0), time(10, 0)), (time(10, 30), time(12, 30)), (time(14, 30), time(16, 0))]
        k = 0
        for day in range(5):                      # 0=lundi … 4=vendredi
            for start, end in slots:
                cs = subjects[k % len(subjects)]
                CourseSlot.objects.create(class_subject=cs, school_year=year,
                                          day=day, start_time=start, end_time=end)
                k += 1
        SchoolBreak.objects.get_or_create(
            school=school, label='Récréation',
            defaults=dict(day=None, start_time=time(10, 0), end_time=time(10, 30)))
        self._ok('Emploi du temps : 15 créneaux + récréation')

    def _grades(self, students, subjects, periods, director, demo_class):
        """T1/T2 : devoir+compo par matière → bulletins calculés, classés, PUBLIÉS.
        T3 (ouverte) : devoirs seulement → l'app affiche le PROVISOIRE."""
        rng = self.rng

        def note_for(student_idx, spread=3.0, center=12.0):
            base = center + (student_idx % 7 - 3) * 0.9      # profil stable par élève
            return Decimal(str(round(min(19.5, max(4.0, rng.gauss(base, spread))) * 2) / 2))

        for period in periods[:2]:                           # T1, T2 → complets + bulletin
            if Bulletin.objects.filter(period=period).exists():
                continue
            averages = []
            for idx, s in enumerate(students):
                per_subject = []
                for cs in subjects:
                    dev, comp = note_for(idx), note_for(idx)
                    Note.objects.get_or_create(
                        student=s, class_subject=cs, period=period, position=1,
                        defaults=dict(note_type=NoteType.DEVOIR, value=dev,
                                      entered_by=cs.teacher or director))
                    Note.objects.get_or_create(
                        student=s, class_subject=cs, period=period, position=2,
                        defaults=dict(note_type=NoteType.COMPOSITION, value=comp,
                                      entered_by=cs.teacher or director))
                    per_subject.append((cs, dev, comp))
                wsum = sum(((d + c) / 2) * cs.coefficient for cs, d, c in per_subject)
                wtot = sum(cs.coefficient for cs, _, _ in per_subject)
                averages.append((s, per_subject, (wsum / wtot).quantize(Decimal('0.01'))))

            ranked = sorted(averages, key=lambda t: t[2], reverse=True)
            first_avg = ranked[0][2]
            for rank, (s, per_subject, avg) in enumerate(ranked, start=1):
                b = Bulletin.objects.create(
                    student=s, period=period, school_class=demo_class,
                    generated_by=director, is_published=True,
                    published_at=timezone.now(), general_average=avg,
                    rank=rank, class_size=len(students), first_average=first_avg,
                    appreciation='Très bon travail' if avg >= 14 else
                                 ('Bon travail, continue' if avg >= 10 else 'Doit faire plus d\'efforts'),
                )
                sub_ranked = {}
                for cs, dev, comp in per_subject:
                    final = ((dev + comp) / 2).quantize(Decimal('0.01'))
                    BulletinLine.objects.create(
                        bulletin=b, class_subject=cs, devoir_average=dev,
                        compo_grade=comp, final_average=final,
                        weighted_grade=(final * cs.coefficient).quantize(Decimal('0.01')),
                    )

        # T3 : devoirs seulement (pas de bulletin → provisoire côté élève/parent)
        t3 = periods[2]
        for idx, s in enumerate(students):
            for cs in subjects[:3]:
                Note.objects.get_or_create(
                    student=s, class_subject=cs, period=t3, position=1,
                    defaults=dict(note_type=NoteType.DEVOIR, value=note_for(idx),
                                  entered_by=cs.teacher or director))
        self._ok('Notes : T1+T2 complets → bulletins publiés/classés ; T3 provisoire')

    def _formative(self, students, subjects, periods, director):
        t3 = periods[2]
        specs = [('Dictée préparée', subjects[0], 8), ('Interrogation écrite', subjects[1], 4),
                 ('Interrogation orale', subjects[2], 1)]
        today = timezone.localdate()
        for title, cs, days_ago in specs:
            ev, created = FormativeEvaluation.objects.get_or_create(
                class_subject=cs, period=t3, title=title,
                defaults=dict(date=today - timedelta(days=days_ago),
                              max_grade=Decimal('20'), is_published_to_parent=True,
                              published_at=timezone.now(), created_by=director))
            if created:
                for idx, s in enumerate(students):
                    FormativeGrade.objects.create(
                        evaluation=ev, student=s,
                        value=Decimal(str(round(min(19.0, max(5.0, self.rng.gauss(12.5 + (idx % 7 - 3) * 0.8, 2.5))) * 2) / 2)))
        self._ok('Évaluations formatives : 3 publiées aux parents (notes pour tous)')

    def _absences(self, school, demo_class, students, profs):
        today = timezone.localdate()
        specs = [(1, 'absent', 3), (4, 'late', 2), (7, 'absent', 9), (1, 'late', 12)]
        for idx, status, days_ago in specs:
            Attendance.objects.get_or_create(
                school=school, school_class=demo_class, student=students[idx],
                date=today - timedelta(days=days_ago), status=status,
                defaults=dict(teacher=profs[0]))
        self._ok('Assiduité : quelques absences/retards réalistes')

    def _lessons(self, school, demo_class, director, profs):
        """Recharge le contenu IA payé (fixture) → leçons v2 déployées."""
        data = json.loads(FIXTURE.read_text(encoding='utf-8'))
        lessons = []
        for spec in data['lessons']:
            teacher = profs[0] if spec['subject'] == 'Français' else profs[1]
            lesson = Lesson.objects.filter(school=school, title=spec['title'],
                                           format_version=2).first()
            if lesson is None:
                unit = Unit.objects.create(
                    teacher=teacher, school=school, title=spec['unit_title'],
                    subject=spec['subject'], subject_type=spec['subject_type'],
                    level=spec['level'], level_detail=spec['level_detail'],
                    language=spec['language'], source_type='text',
                    status=LessonStatus.READY)
                lesson = Lesson.objects.create(
                    teacher=teacher, school=school, unit=unit, title=spec['title'],
                    summary=spec['summary'] or None, slug=spec['slug'] or None,
                    order=spec['order'], subject=spec['subject'],
                    subject_type=spec['subject_type'], level=spec['level'],
                    level_detail=spec['level_detail'], language=spec['language'],
                    source_type='text', status=LessonStatus.READY, format_version=2)
                c = spec['content']
                cv = LessonContentVersion.objects.create(
                    lesson=lesson, version=1,
                    concepts_data=c['concepts_data'], reading_data=c['reading_data'],
                    exam_data=c['exam_data'], story_data=c['story_data'],
                    color=c['color'], guide=c['guide'],
                    validated_by=director, validated_at=timezone.now())
                lesson.active_content_version = cv
                lesson.save(update_fields=['active_content_version'])
            LessonDeployment.objects.get_or_create(
                lesson=lesson, school_class=demo_class,
                defaults=dict(school=school, deployed_by=director, is_active=True))
            lessons.append(lesson)
        self._ok(f'Leçons v2 : {len(lessons)} rechargées de la fixture (0 F de génération) + déployées')
        return lessons

    def _progression(self, students, lessons):
        """3 élèves « vedettes » : concepts finis, révisions étagées (mûres ET
        futures), cahier fait, histoire jouée → les 4 chantiers sont démontrables."""
        today = timezone.localdate()
        stars = students[:3]
        for si, student in enumerate(stars):
            for li, lesson in enumerate(lessons[: 2 + (si % 2)]):
                cv = lesson.active_content_version
                concepts = cv.concepts_data or []
                done_n = len(concepts) if si == 0 else max(1, len(concepts) - 1 - li)
                for c in concepts[:done_n]:
                    passes = max(1, int(c.get('passes', 1)))
                    ConceptProgress.objects.get_or_create(
                        student=student, content_version=cv, concept_id=str(c['id']),
                        defaults=dict(lesson=lesson, passes_done=passes))
                    for q in (c.get('quiz') or [])[:2]:      # journal réaliste
                        QuizAttempt.objects.create(
                            student=student, lesson=lesson, content_version=cv,
                            quiz_id=str(q.get('id')), question_type=q.get('type', ''),
                            student_answer=0, is_correct=True)
                if cv.story_data and si != 2:
                    StoryAttempt.objects.get_or_create(
                        student=student, lesson=lesson, content_version=cv,
                        defaults=dict(score=80 + si * 5, answers=[]))
            srs.sync_reviews(student)
            # Étager l'agenda : mûrs (retard/aujourd'hui), futurs, boîtes variées.
            # Les boîtes >= 2 reçoivent une date de dernière révision RÉCENTE (cette
            # semaine) → la carte parent « Sa semaine » affiche du travail réel.
            offsets = [-3, 0, 2, 7, -1, 4, 0, -2]
            for i, r in enumerate(ConceptReview.objects.filter(student=student).order_by('id')):
                box = 1 + (i + si) % 3
                ConceptReview.objects.filter(pk=r.pk).update(
                    box=box,
                    due_date=today + timedelta(days=offsets[i % len(offsets)]),
                    last_reviewed_at=(timezone.now() - timedelta(days=i % 3)
                                      if box >= 2 else None))
            # Un cahier fait pour la 1ʳᵉ vedette (nœud « fait » + stat parent)
            if si == 0 and lessons:
                cv0 = lessons[0].active_content_version
                CahierAttempt.objects.get_or_create(
                    student=student, content_version=cv0,
                    defaults=dict(lesson=lessons[0],
                                  results=[{'task_id': 'dictee', 'self': 'good'}]))
        self._ok(f'Progression : {len(stars)} élèves vedettes (révisions mûres, cahier, histoires)')

    def _annexes(self, school):
        try:
            # no_fee_classes=0 : sinon le seed finance exclut la 1ʳᵉ classe par
            # nom… qui est notre classe VITRINE (les 24 élèves sans fiche !).
            call_command('seed_demo_finance', school=school.id, no_fee_classes=0)
            call_command('seed_demo_school_life', school=school.id)
            self._ok('Annexes : finance + vie scolaire (émargement, annonces)')
        except Exception as e:      # les annexes ne doivent jamais casser le seed cœur
            self.stdout.write(self.style.WARNING(f'⚠ Annexes ignorées : {e}'))

    # ── sortie ──────────────────────────────────────────────────────────
    def _ok(self, msg):
        self.stdout.write(self.style.SUCCESS(f'✓ {msg}'))

    def _summary(self, school, director, profs, students):
        w = self.stdout.write
        w('\n' + '═' * 62)
        w(f'  {school.name} — PRÊTE POUR LA DÉMO')
        w('═' * 62)
        w('  Directeur   : 70000001 / demo1234')
        w('  Enseignants : 70000002, 70000003 / demo1234')
        w('  Parents     : 70000010-12 / demo1234')
        w('  Élèves (portail) — 3 vedettes avec progression :')
        for s in students[:3]:
            w(f'    • {s.full_name:<22} code {s.access_code}')
        w('═' * 62)
