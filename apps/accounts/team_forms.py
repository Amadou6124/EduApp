import secrets
import string

from django import forms
from django.utils.crypto import get_random_string

from .models import User, UserRole, StaffPermission, Membership

_INPUT = (
    'w-full px-4 py-3 border border-gray-300 rounded-xl text-sm '
    'focus:outline-none focus:ring-2 focus:ring-brand-blue focus:border-brand-blue '
    'placeholder-gray-400 transition'
)
_INPUT_SM = (
    'w-full px-3 py-2 border border-gray-300 rounded-lg text-sm '
    'focus:outline-none focus:ring-2 focus:ring-brand-blue focus:border-brand-blue '
    'placeholder-gray-400 transition'
)
_CHECKBOX = 'h-4 w-4 rounded border-gray-300 text-brand-blue focus:ring-brand-blue cursor-pointer'


def generate_temp_password(length=10):
    """Génère un mot de passe temporaire lisible : lettres + chiffres, sans ambiguïtés."""
    alphabet = string.ascii_letters.replace('l', '').replace('O', '').replace('I', '') + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


class TeamMemberCreateForm(forms.Form):
    """Formulaire de création d'un membre de l'équipe (enseignant ou staff)."""

    first_name = forms.CharField(
        label='Prénom',
        max_length=75,
        widget=forms.TextInput(attrs={
            'class':       _INPUT,
            'placeholder': 'Prénom',
            'autofocus':   True,
        }),
    )
    last_name = forms.CharField(
        label='Nom',
        max_length=75,
        widget=forms.TextInput(attrs={
            'class':       _INPUT,
            'placeholder': 'Nom de famille',
        }),
    )
    phone_number = forms.CharField(
        label='Numéro de téléphone',
        max_length=20,
        widget=forms.TextInput(attrs={
            'class':       _INPUT,
            'placeholder': 'Ex : 0700000000',
            'inputmode':   'tel',
        }),
    )
    job_title = forms.CharField(
        label='Titre du poste',
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class':       _INPUT,
            'placeholder': 'Ex : Censeur, Comptable, Surveillant',
        }),
    )
    role = forms.ChoiceField(
        label='Rôle',
        choices=[
            (UserRole.TEACHER, 'Enseignant'),
            (UserRole.STAFF,   'Staff administratif'),
        ],
        widget=forms.RadioSelect(attrs={'class': 'sr-only'}),
        initial=UserRole.TEACHER,
    )
    password = forms.CharField(
        label='Mot de passe temporaire',
        max_length=128,
        required=False,
        widget=forms.PasswordInput(attrs={
            'class':        _INPUT,
            'placeholder':  'Laissez vide pour générer automatiquement',
            'autocomplete': 'new-password',
        }),
        help_text='Laissez vide pour générer un mot de passe automatiquement.',
    )

    def __init__(self, school, *args, **kwargs):
        self.school = school
        super().__init__(*args, **kwargs)

    def clean_phone_number(self):
        # Le formulaire de CRÉATION ne sert qu'aux nouveaux comptes : un numéro
        # existant ne peut pas être recréé (unicité User.phone_number). Le cas
        # « compte existant » est géré par le flux de recherche → liaison
        # (team_member_search + lien via Membership), pas par ce formulaire.
        phone = self.cleaned_data['phone_number'].strip()
        if User.objects.filter(phone_number=phone).exists():
            raise forms.ValidationError(
                "Ce numéro existe déjà — utilisez la recherche pour lier ce compte à l'école."
            )
        return phone

    def clean_password(self):
        pw = self.cleaned_data.get('password', '').strip()
        if not pw:
            return generate_temp_password()
        if len(pw) < 6:
            raise forms.ValidationError('Le mot de passe doit contenir au moins 6 caractères.')
        return pw

    def save(self):
        """Crée le User **et** sa Membership pour l'école courante.

        `User.school` est conservé en fallback ; `Membership` est la source de
        vérité multi-école. StaffPermission reste géré dans la vue.
        """
        data = self.cleaned_data
        full_name = f"{data['first_name'].strip()} {data['last_name'].strip()}"
        job_title = data.get('job_title', '').strip()
        user = User.objects.create_user(
            phone_number=data['phone_number'],
            password=data['password'],
            full_name=full_name,
            role=data['role'],
            school=self.school,          # fallback FK (conservé 1 release)
            job_title=job_title,
        )
        # Source de vérité multi-école — 1er rattachement → école par défaut.
        Membership.objects.create(
            user=user,
            school=self.school,
            role=data['role'],
            job_title=job_title,
            is_default=True,
            is_active=True,
        )
        return user


class TeamMemberEditForm(forms.ModelForm):
    """Formulaire de modification d'un membre existant."""

    first_name = forms.CharField(
        label='Prénom',
        max_length=75,
        widget=forms.TextInput(attrs={'class': _INPUT, 'placeholder': 'Prénom'}),
    )
    last_name = forms.CharField(
        label='Nom',
        max_length=75,
        widget=forms.TextInput(attrs={'class': _INPUT, 'placeholder': 'Nom de famille'}),
    )

    class Meta:
        model = User
        fields = ['phone_number', 'job_title', 'is_active']
        widgets = {
            'phone_number': forms.TextInput(attrs={
                'class': _INPUT, 'placeholder': 'Ex : 0700000000', 'inputmode': 'tel',
            }),
            'job_title': forms.TextInput(attrs={
                'class': _INPUT, 'placeholder': 'Ex : Censeur, Comptable',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            # Pré-remplir prénom / nom depuis full_name
            parts = self.instance.full_name.split(' ', 1)
            self.fields['first_name'].initial = parts[0]
            self.fields['last_name'].initial  = parts[1] if len(parts) > 1 else ''

    def clean_phone_number(self):
        phone = self.cleaned_data['phone_number'].strip()
        qs = User.objects.filter(phone_number=phone).exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('Ce numéro est déjà utilisé par un autre compte.')
        return phone

    def save(self, commit=True):
        user = super().save(commit=False)
        first = self.cleaned_data.get('first_name', '').strip()
        last  = self.cleaned_data.get('last_name', '').strip()
        user.full_name = f'{first} {last}'.strip()
        if commit:
            user.save()
        return user


class StaffPermissionForm(forms.ModelForm):
    """
    Formulaire de permissions granulaires pour un membre staff.
    Les champs sont regroupés par catégorie pour l'affichage dans le template.
    """

    class Meta:
        model  = StaffPermission
        fields = [
            'can_view_payments', 'can_create_payments', 'can_cancel_payments',
            'can_view_students', 'can_create_students', 'can_edit_students',
            'can_view_notes', 'can_edit_notes',
            'can_generate_bulletins', 'can_download_bulletins',
            'can_record_absences',
            'can_view_classes', 'can_edit_classes',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = _CHECKBOX

    # Groupes de champs exposés au template pour un rendu par catégorie
    GROUPS = [
        ('Paiements', ['can_view_payments', 'can_create_payments', 'can_cancel_payments']),
        ('Élèves',    ['can_view_students', 'can_create_students', 'can_edit_students']),
        ('Notes',     ['can_view_notes', 'can_edit_notes']),
        ('Bulletins', ['can_generate_bulletins', 'can_download_bulletins']),
        ('Absences',  ['can_record_absences']),
        ('Classes',   ['can_view_classes', 'can_edit_classes']),
    ]

    def grouped_fields(self):
        """Retourne [(groupe_label, [BoundField, …]), …] pour le template."""
        return [
            (label, [self[f] for f in field_names])
            for label, field_names in self.GROUPS
        ]
