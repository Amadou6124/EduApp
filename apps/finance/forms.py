"""Formulaires du catalogue de frais (Lot 2).

Les widgets portent directement les classes CSS partagées (.input-field) et des
attributs Alpine (x-model) : la visibilité conditionnelle des champs (montant masqué
pour la scolarité / les frais à variantes, bascule « selon le genre ») est pilotée
côté template par ces liaisons, sans style ni JS parallèle.
"""
from django import forms
from django.utils.translation import gettext_lazy as _

from .models import FeeType, FeeVariant, FeeCategory
from apps.schools.models import EducationLevel


_SELECT = 'input-field cursor-pointer'


class FeeTypeForm(forms.ModelForm):

    # Niveaux concernés (cases à cocher). Validé contre EducationLevel → aucune valeur
    # invalide possible. Aucune case = liste vide = tous les niveaux (rétro-compatible).
    applies_to_levels = forms.MultipleChoiceField(
        label=_('Niveaux concernés'),
        choices=EducationLevel.choices,
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'rounded border-gray-300 text-primary-600 focus:ring-primary-500/40',
        }),
        help_text=_('Aucune case cochée = tous les niveaux.'),
    )

    class Meta:
        model = FeeType
        fields = [
            'name', 'category', 'default_amount',
            'is_mandatory', 'has_variants', 'is_gender_based',
            'applies_to_levels',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'input-field',
                'placeholder': _('Ex : Inscription, Cantine, Tenue…'),
                'x-model': 'name',
            }),
            'category': forms.Select(attrs={
                'class': _SELECT,
                'x-model': 'category',
            }),
            'default_amount': forms.NumberInput(attrs={
                'class': 'input-field',
                'min': '0',
                'placeholder': '0',
                'x-model': 'amount',
            }),
            'is_mandatory': forms.CheckboxInput(attrs={
                'class': 'sr-only peer',
                'x-model': 'isMandatory',
            }),
            'has_variants': forms.CheckboxInput(attrs={
                'class': 'sr-only peer',
                'x-model': 'hasVariants',
            }),
            'is_gender_based': forms.CheckboxInput(attrs={
                'class': 'sr-only peer',
                'x-model': 'isGenderBased',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # La scolarité (TUITION) n'est plus créable ici : elle est gérée par classe et
        # présentée en bannière d'info (cf. écran « Frais & tranches »). On ne propose
        # donc que les catégories éditables au catalogue.
        self.fields['category'].choices = [
            (v, lbl) for v, lbl in FeeCategory.choices if v != FeeCategory.TUITION
        ]
        # App K-12 : on n'affiche pas « Enseignement Supérieur » (hors périmètre).
        self.fields['applies_to_levels'].choices = [
            (v, lbl) for v, lbl in EducationLevel.choices if v != EducationLevel.SUPERIEUR
        ]

    def clean(self):
        cleaned = super().clean()
        category = cleaned.get('category')
        has_variants = cleaned.get('has_variants')
        # On force la cohérence du contrat AVANT que model.clean() ne s'exécute :
        # la scolarité et les frais à variantes ne portent jamais de montant global.
        if category == FeeCategory.TUITION or has_variants:
            cleaned['default_amount'] = None
        else:
            # Frais simple → montant obligatoire (≥ 0 déjà validé par le champ).
            if cleaned.get('default_amount') is None:
                self.add_error('default_amount', _('Indiquez un montant.'))
        # « Selon le genre » n'a de sens qu'avec des variantes.
        if cleaned.get('is_gender_based') and not has_variants:
            cleaned['is_gender_based'] = False
        return cleaned


class FeeVariantForm(forms.ModelForm):

    class Meta:
        model = FeeVariant
        fields = ['label', 'amount', 'gender_key']
        widgets = {
            'label': forms.TextInput(attrs={
                'class': 'input-field',
                'placeholder': _('Ex : Badalabougou, Fille, Repas complet'),
            }),
            'amount': forms.NumberInput(attrs={
                'class': 'input-field',
                'min': '0',
                'placeholder': '0',
            }),
            # gender_key est posé automatiquement par la vue pour les frais genrés ;
            # masqué dans l'UENo champ visible (HiddenInput) le cas échéant.
            'gender_key': forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['gender_key'].required = False
