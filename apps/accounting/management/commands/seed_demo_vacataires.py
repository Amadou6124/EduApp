"""Seed démo : convertit quelques enseignants en vacataires (tarifs par cours
+ émargements du jour) et ajoute des dépenses récurrentes. Idempotent.

    python manage.py seed_demo_vacataires --school <id>
    python manage.py seed_demo_vacataires --school <id> --count 3
"""
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

# Tarif horaire de base par matière (FCFA/h) ; +500 si la classe est une « 3ème ».
_BASE_RATE = {
    'Mathématiques': 2000, 'Anglais': 2000, 'Arts plastiques': 1500,
    'Éducation physique': 1800, 'Sciences naturelles': 2200,
    'Histoire-Géographie': 2000, 'Français': 2300, 'Éducation civique': 1800,
}
_PREFERRED = ['Seydou Traoré', 'Mariam Coulibaly', 'Oumar Keïta']


class Command(BaseCommand):
    help = "Démo : enseignants vacataires (tarifs/cours + émargements) + dépenses récurrentes."

    def add_arguments(self, parser):
        parser.add_argument('--school', type=int, required=True, help="ID de l'école cible")
        parser.add_argument('--count', type=int, default=3, help="Nombre de vacataires (def. 3)")

    @transaction.atomic
    def handle(self, *args, **opt):
        from apps.schools.models import School, ClassSubject
        from apps.accounts.models import Membership, UserRole
        from apps.accounting.models import (
            EmployeeProfile, EmploymentType, VacataireRate,
            TeacherAttendance, RecurringExpense, ExpenseCategory,
        )

        school = School.objects.filter(pk=opt['school']).first()
        if not school:
            raise CommandError(f"École #{opt['school']} introuvable.")

        recorder_m = Membership.objects.filter(
            school=school, role__in=[UserRole.DIRECTOR, UserRole.STAFF], is_active=True,
        ).select_related('user').first()
        if not recorder_m:
            raise CommandError("Aucun directeur/staff pour émarger (anti-fraude).")
        recorder = recorder_m.user

        # Sélection des enseignants : noms connus d'abord, sinon les premiers actifs.
        chosen, seen = [], set()
        for nm in _PREFERRED:
            m = Membership.objects.filter(
                school=school, role=UserRole.TEACHER, is_active=True, user__full_name=nm,
            ).select_related('user').first()
            if m:
                chosen.append(m); seen.add(m.user_id)
        for m in (Membership.objects
                  .filter(school=school, role=UserRole.TEACHER, is_active=True)
                  .select_related('user').order_by('user__full_name')):
            if len(chosen) >= opt['count']:
                break
            if m.user_id not in seen:
                chosen.append(m); seen.add(m.user_id)
        chosen = chosen[:opt['count']]
        if not chosen:
            raise CommandError("Aucun enseignant à convertir.")

        def rate_for(cs):
            base = _BASE_RATE.get(cs.subject.name, 2000)
            if '3ème' in cs.school_class.name:
                base += 500
            return Decimal(base)

        n_rates = n_att = 0
        for m in chosen:
            prof, _ = EmployeeProfile.objects.get_or_create(membership=m)
            prof.employment_type = EmploymentType.VACATAIRE
            prof.monthly_salary = None
            if not prof.hire_date:
                prof.hire_date = date(2025, 10, 1)
            prof.save()

            courses = list(
                ClassSubject.objects
                .filter(teacher=m.user, school_class__school=school, is_active=True)
                .select_related('subject', 'school_class')
                .order_by('subject__name', 'school_class__name')
            )
            for cs in courses:
                VacataireRate.objects.update_or_create(
                    profile=prof, class_subject=cs, defaults={'hourly_rate': rate_for(cs)},
                )
                n_rates += 1
            # Quelques émargements du jour (présents + 1 partiel 1,5 h).
            for i, cs in enumerate(courses[:4]):
                TeacherAttendance.objects.update_or_create(
                    class_subject=cs, date=date.today(), session='morning',
                    defaults={
                        'teacher': m.user, 'school': school, 'status': 'present',
                        'recorded_by': recorder, 'substitute': None,
                        'hours': Decimal('1.5') if i == 3 else None,
                    },
                )
                n_att += 1

        # Dépenses récurrentes (loyer indisponible → Électricité + Eau).
        n_rec = 0
        for cat_name, label, amount in [
            ('Électricité', 'Électricité mensuelle', 140000),
            ('Eau', "Facture d'eau", 60000),
        ]:
            cat = (ExpenseCategory.objects
                   .filter(Q(school__isnull=True) | Q(school=school), name=cat_name, is_active=True)
                   .first())
            if cat:
                RecurringExpense.objects.get_or_create(
                    school=school, label=label,
                    defaults={'category': cat, 'amount': amount, 'payment_method': 'cash'},
                )
                n_rec += 1

        names = ', '.join(m.user.full_name for m in chosen)
        self.stdout.write(self.style.SUCCESS(
            f"✓ Démo vacataires — {school.name}\n"
            f"  {len(chosen)} vacataires ({names})\n"
            f"  {n_rates} tarifs/cours · {n_att} émargements du jour · {n_rec} récurrentes"
        ))
