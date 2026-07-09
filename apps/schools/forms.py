from django import forms
from django.utils.translation import gettext_lazy as _

from .models import (
    School, SchoolClass, SchoolType,
    SchoolYear, Period, PeriodType, EducationLevel,
    Subject, ClassSubject,
    BulletinConfig,
)


class SchoolClassForm(forms.ModelForm):

    class Meta:
        model = SchoolClass
        fields = ['name', 'level', 'annual_fee', 'max_capacity']
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': _('Ex : 6ème A, CP1, Terminale S'),
                'class': 'input-field',
                'autofocus': True,
            }),
            'level': forms.Select(attrs={
                'class': 'input-field bg-white cursor-pointer',
            }),
            'annual_fee': forms.NumberInput(attrs={
                'placeholder': _('Ex : 150000'),
                'min': '0',
                'class': 'input-field pr-14',
            }),
            'max_capacity': forms.NumberInput(attrs={
                'placeholder': _('Optionnel'),
                'min': '1',
                'class': 'input-field',
            }),
        }
        labels = {
            'name': _('Nom de la classe'),
            'level': _('Niveau'),
            'annual_fee': _('Frais de scolarité (FCFA)'),
            'max_capacity': _('Capacité maximale'),
        }

    def clean_annual_fee(self):
        fee = self.cleaned_data.get('annual_fee')
        if fee is not None and fee < 0:
            raise forms.ValidationError(_('Les frais de scolarité ne peuvent pas être négatifs.'))
        return fee


# ── Helpers styles ──────────────────────────────────────────────────────────
_F = ('w-full border border-gray-300 rounded-lg px-3 py-2.5 text-sm '
      'focus:outline-none focus:ring-2 focus:ring-primary-500 '
      'text-gray-800 placeholder-gray-400')
_S = _F + ' bg-white cursor-pointer'


class GeneralSettingsForm(forms.ModelForm):

    class Meta:
        model = School
        fields = ['logo', 'name', 'short_name', 'phone_number', 'email',
                  'address', 'city', 'country', 'school_type']
        widgets = {
            'name':                forms.TextInput(attrs={'class': _F, 'placeholder': 'Ex : École Primaire Sainte Marie'}),
            'short_name':          forms.TextInput(attrs={'class': _F, 'placeholder': 'Ex : EPF Sundiata'}),
            'phone_number':        forms.TextInput(attrs={'class': _F, 'placeholder': '+223 00 00 00 00'}),
            'email':               forms.EmailInput(attrs={'class': _F, 'placeholder': 'contact@ecole.ml'}),
            'address':             forms.TextInput(attrs={'class': _F, 'placeholder': 'Rue Soundiata Keïta, Hamdallaye', 'list': 'countries-list'}),
            'city':                forms.TextInput(attrs={'class': _F, 'placeholder': 'Ex : Bamako'}),
            'country':             forms.TextInput(attrs={'class': _F, 'placeholder': 'Ex : Mali', 'list': 'countries-list'}),
            'school_type':         forms.Select(attrs={'class': _S}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['school_type'].choices = [('', '— Sélectionner —')] + list(SchoolType.choices)
        for f in ['phone_number', 'email', 'address', 'city', 'school_type']:
            self.fields[f].required = False

    def clean_name(self):
        v = self.cleaned_data.get('name', '').strip()
        if not v:
            raise forms.ValidationError('Le nom de l\'établissement est obligatoire.')
        return v

    def clean_phone_number(self):
        return self.cleaned_data.get('phone_number', '').strip()

    def clean_logo(self):
        logo = self.cleaned_data.get('logo')
        if logo and hasattr(logo, 'content_type'):
            if logo.content_type not in ('image/jpeg', 'image/png', 'image/svg+xml', 'image/webp'):
                raise forms.ValidationError('Format invalide. Utilisez PNG, JPG ou SVG.')
            if logo.size > 2 * 1024 * 1024:
                raise forms.ValidationError('Le logo ne doit pas dépasser 2 Mo.')
        return logo


class AppearanceForm(forms.ModelForm):

    class Meta:
        model = School
        fields = ['logo']

    def clean_logo(self):
        logo = self.cleaned_data.get('logo')
        if logo and hasattr(logo, 'content_type'):
            if logo.content_type not in ('image/jpeg', 'image/png', 'image/svg+xml', 'image/webp'):
                raise forms.ValidationError('Format invalide. Utilisez PNG, JPG ou SVG.')
            if logo.size > 2 * 1024 * 1024:
                raise forms.ValidationError('Le logo ne doit pas dépasser 2 Mo.')
        return logo


class ReceiptSignerForm(forms.ModelForm):

    class Meta:
        model = School
        fields = ['receipt_signer_title']
        widgets = {
            'receipt_signer_title': forms.TextInput(attrs={
                'class': _F, 'placeholder': 'Ex : Le Directeur',
            }),
        }


# ── Années scolaires + Périodes ────────────────────────────────────────────

class SchoolYearForm(forms.ModelForm):

    class Meta:
        model  = SchoolYear
        fields = ['name', 'start_date', 'end_date', 'is_active']
        widgets = {
            'name':       forms.TextInput(attrs={'class': _F, 'placeholder': '2025-2026'}),
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': _F}),
            'end_date':   forms.DateInput(attrs={'type': 'date', 'class': _F}),
            'is_active':  forms.CheckboxInput(attrs={'class': 'w-4 h-4 accent-primary-600'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['is_active'].required = False


class PeriodForm(forms.ModelForm):

    class Meta:
        model  = Period
        fields = ['education_level', 'name', 'period_type', 'start_date', 'end_date', 'order']
        widgets = {
            'education_level': forms.Select(attrs={'class': _S}),
            'name':        forms.TextInput(attrs={'class': _F, 'placeholder': 'Ex : Trimestre 1'}),
            'period_type': forms.Select(attrs={'class': _S}),
            'start_date':  forms.DateInput(attrs={'type': 'date', 'class': _F}),
            'end_date':    forms.DateInput(attrs={'type': 'date', 'class': _F}),
            'order':       forms.NumberInput(attrs={'class': _F, 'min': '1'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Cycle facultatif (vide = toute l'école) ; dates facultatives (grèves/imprévus).
        self.fields['education_level'].required = False
        self.fields['education_level'].choices = (
            [('', _("Toute l'école"))] + list(EducationLevel.choices)
        )
        self.fields['start_date'].required = False
        self.fields['end_date'].required = False


# ── Matières ──────────────────────────────────────────────────────────────

class SubjectForm(forms.ModelForm):

    class Meta:
        model  = Subject
        # La couleur est attribuée AUTOMATIQUEMENT (couleurs distinctes, sans collision —
        # voir Subject.save). Pas de saisie manuelle : sinon on ré-introduit des collisions.
        fields = ['name', 'short_name']
        widgets = {
            'name':       forms.TextInput(attrs={'class': _F, 'placeholder': 'Ex : Mathématiques'}),
            'short_name': forms.TextInput(attrs={'class': _F, 'placeholder': 'Auto (ex. MATH)', 'maxlength': '10'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Abréviation optionnelle → générée auto (Subject.save) si laissée vide.
        self.fields['short_name'].required = False


# ── Bulletin config ────────────────────────────────────────────────────────

class BulletinConfigForm(forms.ModelForm):

    class Meta:
        model  = BulletinConfig
        fields = [
            'show_ministry_header',
            'ministry_line1', 'ministry_line2', 'ministry_line3',
            'republic_line1', 'republic_line2',
            'bulletin_title',
            'show_logo',
            'paper_format',
            'show_rank',
            'show_first_average', 'show_appreciations',
            'show_last_average',
            'footer_left', 'footer_right',
        ]
        widgets = {
            'ministry_line1': forms.TextInput(attrs={'class': _F, 'placeholder': "MINISTERE DE L'EDUCATION NATIONALE"}),
            'ministry_line2': forms.TextInput(attrs={'class': _F, 'placeholder': "Académie d'Enseignement de Bamako"}),
            'ministry_line3': forms.TextInput(attrs={'class': _F, 'placeholder': "CAP de la Commune IV (optionnel)"}),
            'republic_line1': forms.TextInput(attrs={'class': _F, 'placeholder': "REPUBLIQUE DU MALI"}),
            'republic_line2': forms.TextInput(attrs={'class': _F, 'placeholder': "UN PEUPLE - UN BUT - UNE FOI"}),
            'bulletin_title': forms.TextInput(attrs={'class': _F, 'placeholder': "RELEVE DE NOTES"}),
            'paper_format':   forms.Select(attrs={'class': _S}),
            'footer_left':    forms.TextInput(attrs={'class': _F, 'placeholder': "Le Parent"}),
            'footer_right':   forms.TextInput(attrs={'class': _F, 'placeholder': "Le Directeur"}),
            # Interrupteurs (cases masquées + piste stylée dans le template)
            'show_ministry_header': forms.CheckboxInput(attrs={'class': 'sr-only peer', 'x-model': 'ministry'}),
            'show_logo':            forms.CheckboxInput(attrs={'class': 'sr-only peer'}),
            'show_rank':            forms.CheckboxInput(attrs={'class': 'sr-only peer'}),
            'show_first_average':   forms.CheckboxInput(attrs={'class': 'sr-only peer'}),
            'show_appreciations':   forms.CheckboxInput(attrs={'class': 'sr-only peer'}),
            'show_last_average':    forms.CheckboxInput(attrs={'class': 'sr-only peer'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.required = False


class ClassSubjectForm(forms.ModelForm):

    class Meta:
        model  = ClassSubject
        fields = [
            'subject', 'coefficient', 'max_grade',
            'duration_hours', 'teacher', 'order',
        ]
        widgets = {
            'subject':        forms.Select(attrs={'class': _S}),
            'coefficient':    forms.NumberInput(attrs={'class': _F, 'step': '0.1', 'min': '0.1'}),
            'max_grade':      forms.NumberInput(attrs={'class': _F, 'step': '0.01', 'min': '1'}),
            'duration_hours': forms.NumberInput(attrs={'class': _F, 'step': '0.5', 'min': '0.5'}),
            'teacher':        forms.Select(attrs={'class': _S}),
            'order':          forms.NumberInput(attrs={'class': _F, 'min': '0'}),
        }

    def __init__(self, school, school_class, *args, **kwargs):

        super().__init__(*args, **kwargs)
        from apps.accounts.models import User

        # Matières disponibles (pas encore assignées à cette classe)
        excluded = ClassSubject.objects.filter(school_class=school_class)
        if self.instance and self.instance.pk:
            excluded = excluded.exclude(pk=self.instance.pk)
        excluded_ids = excluded.values_list('subject_id', flat=True)

        self.fields['subject'].queryset = Subject.objects.filter(
            school=school, is_active=True,
        ).exclude(id__in=excluded_ids)

        # Enseignants de l'école
        self.fields['teacher'].queryset = User.objects.filter(
            school=school, is_active=True,
        ).order_by('full_name' if hasattr(User, 'full_name') else 'phone_number')
        self.fields['teacher'].empty_label = '— Aucun —'
        self.fields['teacher'].required    = False
