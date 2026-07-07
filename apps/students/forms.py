from django import forms
from django.utils.translation import gettext_lazy as _

from apps.payments.models import PaymentMethod
from apps.schools.models import SchoolClass

from .models import ParentRelationship, Student, Gender


class StudentCreateForm(forms.ModelForm):
    # Ordre d'affichage logique du panneau d'inscription (le template rend les champs
    # génériquement dans cet ordre).
    field_order = [
        'last_name', 'first_name', 'gender', 'date_of_birth', 'birth_place',
        'school_class', 'matricule',
        'initial_payment', 'payment_method',
    ]

    # Genre OBLIGATOIRE à l'inscription unitaire (lot 4a) : pilote la variante de tenue
    # auto et, plus largement, la fiche financière. Le panneau envoie 'F'/'M' (codes du
    # lot 1). Requis ici uniquement — groupe/import laissent le genre nullable.
    gender = forms.ChoiceField(
        label=_('Genre'),
        choices=Gender.choices,
        required=True,
        error_messages={'required': _('Choisissez le genre de l\'élève.')},
    )

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

    # Date de naissance OBLIGATOIRE à l'inscription unitaire (état civil, documents officiels).
    date_of_birth = forms.DateField(
        label=_('Date de naissance'),
        required=True,
        error_messages={'required': _('La date de naissance est obligatoire.')},
        widget=forms.DateInput(attrs={'type': 'date'}),
    )

    class Meta:
        model = Student
        # full_name est absent : il est recomposé automatiquement (Prénom + Nom) dans
        # Student.save(). On saisit last_name + first_name séparément.
        fields = [
            'school_class', 'last_name', 'first_name', 'gender',
            'date_of_birth', 'birth_place',
            'matricule',
        ]
        labels = {
            'school_class': _('Classe'),
            'last_name':    _('Nom de famille'),
            'first_name':   _('Prénom(s)'),
            'birth_place':  _('Lieu de naissance'),
            'matricule':    _('Matricule'),
        }
        help_texts = {
            'matricule': _('Laisser vide pour une génération automatique (ex. 2026-0001).'),
        }

    def __init__(self, *args, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Nom et prénom obligatoires à l'inscription (blank=True au niveau modèle pour les
        # chemins hérités uniquement — voir Student.last_name/first_name).
        self.fields['last_name'].required = True
        self.fields['first_name'].required = True
        if school:
            self.fields['school_class'].queryset = (
                SchoolClass.objects.filter(school=school, is_active=True)
                .order_by('level', 'name')
            )
            self.fields['school_class'].label_from_instance = lambda obj: obj.name
        self.fields['school_class'].empty_label = _('— Sélectionner une classe —')


class StudentUpdateForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = [
            'school_class', 'last_name', 'first_name',
            'date_of_birth', 'birth_place',
            'matricule', 'notes',
        ]
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'notes':         forms.Textarea(attrs={'rows': 3}),
        }
        labels = {
            'last_name':   _('Nom de famille'),
            'first_name':  _('Prénom(s)'),
            'birth_place': _('Lieu de naissance'),
            'matricule':   _('Matricule'),
        }

    def __init__(self, *args, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['last_name'].required = True
        self.fields['first_name'].required = True
        if school:
            self.fields['school_class'].queryset = (
                SchoolClass.objects.filter(school=school, is_active=True)
                .order_by('level', 'name')
            )
            self.fields['school_class'].label_from_instance = lambda obj: obj.name
