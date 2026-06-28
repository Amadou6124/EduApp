"""
Commande dev : pré-remplit le catalogue de frais d'une école (type malien).

Usage :
    python manage.py seed_fee_catalog --school <id>
    python manage.py seed_fee_catalog --all       # toutes les écoles

Idempotent (get_or_create). Hors des migrations volontairement, pour ne pas polluer
les écoles réelles automatiquement.
"""
from django.core.management.base import BaseCommand, CommandError

from apps.schools.models import School
from apps.finance.seeds import seed_fee_catalog


class Command(BaseCommand):
    help = "Pré-remplit le catalogue de frais de démonstration pour une/des école(s)."

    def add_arguments(self, parser):
        parser.add_argument('--school', type=int, help="ID de l'école cible")
        parser.add_argument('--all', action='store_true', help='Toutes les écoles')

    def handle(self, *args, **options):
        if options['all']:
            schools = School.objects.all()
        elif options['school']:
            schools = School.objects.filter(pk=options['school'])
            if not schools.exists():
                raise CommandError(f"École #{options['school']} introuvable.")
        else:
            raise CommandError('Précisez --school <id> ou --all.')

        for school in schools:
            recap = seed_fee_catalog(school)
            self.stdout.write(self.style.SUCCESS(
                f"[{school.name}] catalogue : {recap['fee_types']} frais, "
                f"{recap['templates']} gabarits."
            ))
