"""
Seed de DÉMO « vie scolaire » pour une école : émargements enseignants + annonces.

Complète la démo finance pour rendre les pages Émargement et Annonces « pleines ».
Reproductible (graine), purge + régénère l'émargement, idempotent sur les annonces.

Usage :
    python manage.py seed_demo_school_life --school <id>
    python manage.py seed_demo_school_life --school <id> --days 25 --seed 42

NE TOUCHE QU'À L'ÉCOLE CIBLÉE. Données de démo uniquement.
"""
import random
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.schools.models import School, ClassSubject, SchoolAnnouncement
from apps.accounting.models import (
    TeacherAttendance, TeacherAttendanceStatus, SessionType,
)
from apps.teachers.models import StudentObservation

ANNOUNCEMENTS = [
    ("Réunion des parents d'élèves",
     "Une réunion générale des parents se tiendra samedi prochain à 9h dans la cour de l'école. "
     "Présence vivement souhaitée pour faire le point sur le trimestre."),
    ("Rappel — échéance de scolarité",
     "La 2e tranche de scolarité arrive à échéance fin du mois. Merci de régulariser au guichet "
     "(espèces, Orange Money ou Wave). Un reçu vous sera remis."),
    ("Journée culturelle et sportive",
     "L'école organise sa journée culturelle le vendredi. Au programme : poésie, chants, et tournoi "
     "de football inter-classes. Tenue de sport recommandée."),
    ("Distribution des bulletins du 2e trimestre",
     "Les bulletins seront remis aux parents en fin de semaine. Les enseignants principaux recevront "
     "les familles sur rendez-vous."),
    ("Vacances de mi-trimestre",
     "Les cours seront suspendus du lundi au vendredi pour les vacances de mi-trimestre. "
     "Reprise normale le lundi suivant."),
    ("Campagne de fournitures scolaires",
     "Une commande groupée de fournitures est ouverte cette semaine. Renseignez-vous auprès du "
     "secrétariat pour bénéficier des tarifs négociés."),
]


class Command(BaseCommand):
    help = "Seed démo vie scolaire (émargements enseignants + annonces) sur une école."

    def add_arguments(self, parser):
        parser.add_argument('--school', type=int, required=True, help="ID de l'école cible")
        parser.add_argument('--days', type=int, default=25, help="Nb de jours ouvrés d'historique d'émargement")
        parser.add_argument('--seed', type=int, default=42, help="Graine aléatoire (reproductible)")

    def handle(self, *args, **opt):
        random.seed(opt['seed'])
        school = School.objects.filter(pk=opt['school']).first()
        if not school:
            raise CommandError(f"École #{opt['school']} introuvable.")
        recorder = self._recorder_for(school)
        if recorder is None:
            raise CommandError("Aucun directeur/staff pour 'recorded_by' / 'author'.")

        with transaction.atomic():
            n_em = self._seed_emargement(school, recorder, opt['days'])
            n_ann = self._seed_announcements(school, recorder)
            obs_read, obs_total = self._seed_observations(school)

        self.stdout.write(self.style.SUCCESS(
            f"\n✓ Vie scolaire — {school.name}\n"
            f"  émargements: {n_em} · annonces ajoutées: {n_ann} · "
            f"observations: {obs_read}/{obs_total} lues"
        ))

    # ──────────────────────────────────────────────────────────────────────────
    def _recorder_for(self, school):
        from django.contrib.auth import get_user_model
        U = get_user_model()
        return (U.objects.filter(role='director', school=school).first()
                or U.objects.filter(role='staff', school=school).first())

    def _weekdays(self, n):
        """Les n derniers jours ouvrés (lun-ven), aujourd'hui inclus, du plus ancien au plus récent."""
        days, d = [], timezone.now().date()
        while len(days) < n:
            if d.weekday() < 5:
                days.append(d)
            d -= timedelta(days=1)
        return list(reversed(days))

    def _seed_emargement(self, school, recorder, n_days):
        TeacherAttendance.objects.filter(school=school).delete()
        courses = list(
            ClassSubject.objects.filter(school_class__school=school)
            .select_related('teacher')
        )
        courses = [c for c in courses if c.teacher_id]
        if not courses:
            return 0
        teachers = list({c.teacher for c in courses})

        objs = []
        for day in self._weekdays(n_days):
            for cs in courses:
                if random.random() > 0.82:        # ~82 % des cours émargés ce jour
                    continue
                r = random.random()
                if r < 0.86:
                    status, sub = TeacherAttendanceStatus.PRESENT, None
                elif r < 0.95:
                    status, sub = TeacherAttendanceStatus.ABSENT, None
                else:
                    status = TeacherAttendanceStatus.REPLACED
                    others = [t for t in teachers if t != cs.teacher]
                    sub = random.choice(others) if others else None
                objs.append(TeacherAttendance(
                    teacher=cs.teacher, school=school, class_subject=cs,
                    date=day, session=SessionType.MORNING, status=status,
                    substitute=sub, recorded_by=recorder,
                ))
        TeacherAttendance.objects.bulk_create(objs)
        return len(objs)

    def _seed_announcements(self, school, author):
        # audience : on prend une valeur « école entière » de façon robuste
        choices = [c[0] for c in SchoolAnnouncement._meta.get_field('audience').choices]
        audience = next((c for c in choices if str(c).lower() in ('all', 'school', 'ecole', 'tous', 'whole')), choices[0])
        now = timezone.now()
        created = 0
        for i, (title, body) in enumerate(ANNOUNCEMENTS):
            _, was_created = SchoolAnnouncement.objects.get_or_create(
                school=school, title=title,
                defaults=dict(
                    body=body, author=author, audience=audience,
                    is_published=True, published_at=now - timedelta(days=i * 3),
                ),
            )
            created += int(was_created)
        return created

    def _seed_observations(self, school):
        """Mixe lu/non-lu sur les observations existantes (~55 % lues) → état réaliste."""
        obs = list(StudentObservation.objects.filter(student__school_class__school=school))
        read = 0
        for o in obs:
            o.is_read = random.random() < 0.55
            read += int(o.is_read)
        if obs:
            StudentObservation.objects.bulk_update(obs, ['is_read'])
        return read, len(obs)
