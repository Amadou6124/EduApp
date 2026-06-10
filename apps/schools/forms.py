import re

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import School, SchoolClass, SchoolType


class SchoolClassForm(forms.ModelForm):

    class Meta:
        model = SchoolClass
        fields = ['name', 'level', 'annual_fee', 'max_capacity']
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': _('Ex : 6ème A, CP1, Terminale S'),
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-600 text-gray-800',
                'autofocus': True,
            }),
            'level': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-600 text-gray-800 bg-white',
            }),
            'annual_fee': forms.NumberInput(attrs={
                'placeholder': _('Ex : 150000'),
                'min': '0',
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-600 text-gray-800',
            }),
            'max_capacity': forms.NumberInput(attrs={
                'placeholder': _('Optionnel'),
                'min': '1',
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-600 text-gray-800',
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
      'focus:outline-none focus:ring-2 focus:ring-brand-blue '
      'text-gray-800 placeholder-gray-400')
_S = _F + ' bg-white cursor-pointer'


class GeneralSettingsForm(forms.ModelForm):

    class Meta:
        model = School
        fields = ['name', 'phone_number', 'email',
                  'address', 'city', 'country',
                  'current_school_year', 'school_type']
        widgets = {
            'name':                forms.TextInput(attrs={'class': _F, 'placeholder': 'Ex : École Primaire Sainte Marie'}),
            'phone_number':        forms.TextInput(attrs={'class': _F, 'placeholder': '+225 07 00 00 00 00'}),
            'email':               forms.EmailInput(attrs={'class': _F, 'placeholder': 'contact@ecole.ci'}),
            'address':             forms.TextInput(attrs={'class': _F, 'placeholder': '12 Rue de la Paix, Cocody', 'list': 'countries-list'}),
            'city':                forms.TextInput(attrs={'class': _F, 'placeholder': 'Ex : Abidjan'}),
            'country':             forms.TextInput(attrs={'class': _F, 'placeholder': 'Ex : Côte d\'Ivoire', 'list': 'countries-list'}),
            'current_school_year': forms.TextInput(attrs={'class': _F, 'placeholder': '2024-2025'}),
            'school_type':         forms.Select(attrs={'class': _S}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['school_type'].choices = [('', '— Sélectionner —')] + list(SchoolType.choices)
        for f in ['email', 'address', 'city', 'current_school_year', 'school_type']:
            self.fields[f].required = False

    def clean_name(self):
        v = self.cleaned_data.get('name', '').strip()
        if not v:
            raise forms.ValidationError('Le nom de l\'établissement est obligatoire.')
        return v

    def clean_phone_number(self):
        v = self.cleaned_data.get('phone_number', '').strip()
        if not v:
            raise forms.ValidationError('Le numéro de téléphone est obligatoire.')
        return v


class AppearanceForm(forms.ModelForm):

    class Meta:
        model = School
        fields = ['logo', 'primary_color']
        widgets = {
            'primary_color': forms.TextInput(attrs={
                'class': _F, 'placeholder': '#1E3A5F', 'maxlength': '7',
            }),
        }

    def clean_logo(self):
        logo = self.cleaned_data.get('logo')
        if logo and hasattr(logo, 'content_type'):
            if logo.content_type not in ('image/jpeg', 'image/png', 'image/svg+xml', 'image/webp'):
                raise forms.ValidationError('Format invalide. Utilisez PNG, JPG ou SVG.')
            if logo.size > 2 * 1024 * 1024:
                raise forms.ValidationError('Le logo ne doit pas dépasser 2 Mo.')
        return logo

    def clean_primary_color(self):
        color = self.cleaned_data.get('primary_color', '').strip()
        if not re.match(r'^#[0-9A-Fa-f]{6}$', color):
            raise forms.ValidationError('Format invalide. Utilisez #RRGGBB (ex : #1E3A5F).')
        return color


class ReceiptModeForm(forms.ModelForm):

    class Meta:
        model = School
        fields = ['receipt_mode']


class ReceiptUploadForm(forms.ModelForm):

    class Meta:
        model = School
        fields = ['receipt_template_pdf']

    def clean_receipt_template_pdf(self):
        pdf = self.cleaned_data.get('receipt_template_pdf')
        if pdf and hasattr(pdf, 'content_type'):
            if pdf.content_type != 'application/pdf':
                raise forms.ValidationError('Seuls les fichiers PDF natifs sont acceptés.')
            if pdf.size > 10 * 1024 * 1024:
                raise forms.ValidationError('Le fichier ne doit pas dépasser 10 Mo.')
        return pdf
