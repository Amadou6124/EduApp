from django import forms
from django.utils.translation import gettext_lazy as _

from .models import SchoolClass


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
