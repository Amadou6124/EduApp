"""
Seed de démonstration du catalogue de frais (type malien).

Déclenchable à la main UNIQUEMENT (bouton dev dans l'écran settings, ou commande
`manage.py seed_fee_catalog`). JAMAIS exécuté en migration : on ne veut pas polluer
les écoles réelles. Idempotent : get_or_create par nom → relançable sans doublon.
"""
from decimal import Decimal

from .models import FeeType, FeeVariant, PaymentScheduleTemplate, FeeCategory


def seed_fee_catalog(school):
    """Pré-remplit le catalogue + les gabarits pour une école. Retourne un récap."""

    # ── Frais simples / obligatoires ───────────────────────────────────────────
    # Inscription : obligatoire, montant simple.
    FeeType.objects.get_or_create(
        school=school, name='Inscription',
        defaults=dict(category=FeeCategory.ONE_TIME, default_amount=Decimal('15000'),
                      is_mandatory=True, order=1),
    )
    # Fournitures : optionnel, montant simple.
    FeeType.objects.get_or_create(
        school=school, name='Fournitures',
        defaults=dict(category=FeeCategory.ONE_TIME, default_amount=Decimal('10000'),
                      is_mandatory=False, order=2),
    )

    # ── Scolarité : déclarée, sans montant (vient de SchoolClass.annual_fee) ────
    FeeType.objects.get_or_create(
        school=school, name='Scolarité',
        defaults=dict(category=FeeCategory.TUITION, default_amount=None,
                      is_mandatory=True, order=3),
    )

    # ── Tenue : à variantes, genrée (auto selon Student.gender) ────────────────
    tenue, _ = FeeType.objects.get_or_create(
        school=school, name='Tenue',
        defaults=dict(category=FeeCategory.ONE_TIME, default_amount=None,
                      is_mandatory=False, has_variants=True, is_gender_based=True,
                      order=4),
    )
    FeeVariant.objects.get_or_create(
        fee_type=tenue, label='Fille',
        defaults=dict(amount=Decimal('15000'), gender_key='F', order=1),
    )
    FeeVariant.objects.get_or_create(
        fee_type=tenue, label='Garçon',
        defaults=dict(amount=Decimal('12000'), gender_key='M', order=2),
    )

    # ── Bus : à variantes (trajets), choix manuel ──────────────────────────────
    bus, _ = FeeType.objects.get_or_create(
        school=school, name='Bus',
        defaults=dict(category=FeeCategory.SUBSCRIPTION, default_amount=None,
                      is_mandatory=False, has_variants=True, is_gender_based=False,
                      order=5),
    )
    FeeVariant.objects.get_or_create(
        fee_type=bus, label='Badalabougou',
        defaults=dict(amount=Decimal('20000'), order=1),
    )
    FeeVariant.objects.get_or_create(
        fee_type=bus, label='Hamdallaye',
        defaults=dict(amount=Decimal('15000'), order=2),
    )

    # ── Cantine : abonnement simple mensuel ────────────────────────────────────
    FeeType.objects.get_or_create(
        school=school, name='Cantine',
        defaults=dict(category=FeeCategory.SUBSCRIPTION, default_amount=Decimal('5000'),
                      is_mandatory=False, order=6),
    )

    # ── Gabarits de tranches ───────────────────────────────────────────────────
    PaymentScheduleTemplate.objects.get_or_create(
        school=school, name='Annuel',
        defaults=dict(installments_count=1, is_active=True),
    )
    # Trimestriel = défaut. save() du modèle garantit l'unicité du défaut.
    trim, created = PaymentScheduleTemplate.objects.get_or_create(
        school=school, name='Trimestriel',
        defaults=dict(installments_count=3, is_active=True, is_default=True),
    )
    if not created and not trim.is_default:
        trim.is_default = True
        trim.save()
    PaymentScheduleTemplate.objects.get_or_create(
        school=school, name='Mensuel',
        defaults=dict(installments_count=9, is_active=True),
    )

    return {
        'fee_types': FeeType.objects.filter(school=school).count(),
        'templates': PaymentScheduleTemplate.objects.filter(school=school).count(),
    }
