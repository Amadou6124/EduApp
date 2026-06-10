from django import forms
from django.utils.translation import gettext_lazy as _

from apps.payments.models import PaymentMethod
from apps.schools.models import SchoolClass

from .models import ParentRelationship, Student


class StudentCreateForm(forms.ModelForm):
    # Champs hors-modèle pour le paiement initial optionnel
    initial_payment = forms.DecimalField(
        label=_('Montant versé (FCFA)'),
        min_value=0,
        required=False,
        widget=forms.NumberInput(attrs={'placeholder': '0'}),
    )
    payment_method = forms.ChoiceField(
        label=_('Mode de paiement'),
        choices=PaymentMethod.choices,
        required=False,
    )

    class Meta:
        model = Student
        fields = [
            'school_class', 'full_name', 'date_of_birth',
            'phone_number', 'parent_phone_number', 'parent_relationship',
        ]
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
        }
        labels = {
            'school_class':        _('Classe'),
            'full_name':           _('Nom complet'),
            'date_of_birth':       _('Date de naissance'),
            'phone_number':        _('Téléphone élève'),
            'parent_phone_number': _('Téléphone parent'),
            'parent_relationship': _('Lien de parenté'),
        }

    def __init__(self, *args, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        if school:
            self.fields['school_class'].queryset = (
                SchoolClass.objects.filter(school=school, is_active=True)
                .order_by('level', 'name')
            )
        self.fields['school_class'].empty_label = _('— Sélectionner une classe —')


class StudentUpdateForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = [
            'school_class', 'full_name', 'date_of_birth',
            'phone_number', 'parent_phone_number', 'parent_relationship',
            'notes',
        ]
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'notes':         forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        if school:
            self.fields['school_class'].queryset = (
                SchoolClass.objects.filter(school=school, is_active=True)
                .order_by('level', 'name')
            )
