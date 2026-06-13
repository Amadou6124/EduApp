from django.core.management.base import BaseCommand
from django.utils.translation import gettext_lazy as _

from apps.schools.models import School, SchoolClass, EducationLevel
from apps.accounts.models import User, UserRole


class Command(BaseCommand):
    help = 'Crée une école de démonstration avec des classes exemples'

    def handle(self, *args, **options):
        # Création de l'école démo
        school, created = School.objects.get_or_create(
            id=1,
            defaults={
                'name': 'École Primaire Excellence',
                'city': 'Bamako',
                'country': 'Mali',
                'phone_number': '+223 00 00 00 00',
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'✓ École créée : {school.name}'))
        else:
            self.stdout.write(f'→ École existante : {school.name}')

        # Classes exemples
        demo_classes = [
            {'name': 'CP1', 'level': EducationLevel.FONDAMENTAL_1, 'annual_fee': 120000, 'max_capacity': 40},
            {'name': 'CP2', 'level': EducationLevel.FONDAMENTAL_1, 'annual_fee': 120000, 'max_capacity': 40},
            {'name': 'CE1', 'level': EducationLevel.FONDAMENTAL_1, 'annual_fee': 135000, 'max_capacity': 38},
            {'name': 'CE2', 'level': EducationLevel.FONDAMENTAL_1, 'annual_fee': 135000, 'max_capacity': 38},
            {'name': 'CM1', 'level': EducationLevel.FONDAMENTAL_1, 'annual_fee': 150000, 'max_capacity': 35},
            {'name': 'CM2', 'level': EducationLevel.FONDAMENTAL_1, 'annual_fee': 150000, 'max_capacity': 35},
        ]

        for class_data in demo_classes:
            sc, c = SchoolClass.objects.get_or_create(
                school=school,
                name=class_data['name'],
                defaults={
                    'level': class_data['level'],
                    'annual_fee': class_data['annual_fee'],
                    'max_capacity': class_data['max_capacity'],
                }
            )
            status = '✓ Créée' if c else '→ Existante'
            self.stdout.write(f'  {status} : {sc.name}')

        # Superuser directeur
        if not User.objects.filter(phone_number='0000000000').exists():
            User.objects.create_superuser(
                phone_number='0000000000',
                password='admin123',
                full_name='Directeur Demo',
                role=UserRole.DIRECTOR,
                school=school,
            )
            self.stdout.write(self.style.SUCCESS(
                '\n✓ Superuser créé :\n'
                '  Téléphone : 0000000000\n'
                '  Mot de passe : admin123\n'
                '  ⚠️  Changer le mot de passe en production !'
            ))
        else:
            self.stdout.write('→ Superuser déjà existant')

        self.stdout.write(self.style.SUCCESS('\n✅ Seed terminé — http://127.0.0.1:8000/classes/'))
