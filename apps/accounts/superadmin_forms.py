from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.schools.models import School
from .models import User


class SchoolCreateForm(forms.ModelForm):
    class Meta:
        model = School
        fields = ['name', 'city', 'country', 'phone_number', 'email', 'logo']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Ex: Groupe Scolaire Excellence'}),
            'city': forms.TextInput(attrs={'placeholder': 'Ex: Bamako'}),
            'country': forms.TextInput(attrs={'placeholder': 'Mali'}),
            'phone_number': forms.TextInput(attrs={'placeholder': '+223 00 00 00 00'}),
            'email': forms.EmailInput(attrs={'placeholder': 'contact@ecole.ml'}),
        }


class SchoolUpdateForm(forms.ModelForm):
    class Meta:
        model = School
        fields = ['name', 'city', 'country', 'phone_number', 'email', 'logo', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Ex: Groupe Scolaire Excellence'}),
            'city': forms.TextInput(attrs={'placeholder': 'Ex: Bamako'}),
            'country': forms.TextInput(attrs={'placeholder': 'Mali'}),
            'phone_number': forms.TextInput(attrs={'placeholder': '+223 00 00 00 00'}),
            'email': forms.EmailInput(attrs={'placeholder': 'contact@ecole.ml'}),
        }


class DirectorCreateForm(forms.ModelForm):
    email = forms.EmailField(
        label=_('Adresse email'),
        help_text=_('Requis pour recevoir les rapports et factures.'),
        widget=forms.EmailInput(attrs={'placeholder': 'directeur@ecole.ci'}),
    )
    password = forms.CharField(
        label=_('Mot de passe temporaire'),
        widget=forms.PasswordInput(attrs={'placeholder': 'Minimum 8 caractères'}),
        min_length=8,
    )
    password_confirm = forms.CharField(
        label=_('Confirmer le mot de passe'),
        widget=forms.PasswordInput(attrs={'placeholder': 'Répéter le mot de passe'}),
    )

    class Meta:
        model = User
        fields = ['full_name', 'phone_number', 'email']
        widgets = {
            'full_name': forms.TextInput(attrs={'placeholder': 'Nom Prénom'}),
            'phone_number': forms.TextInput(attrs={'placeholder': '+225 07 00 00 00 00'}),
        }

    def clean_phone_number(self):
        phone = self.cleaned_data['phone_number']
        if User.objects.filter(phone_number=phone).exists():
            raise ValidationError(_('Ce numéro de téléphone est déjà utilisé.'))
        return phone

    def clean_email(self):
        email = self.cleaned_data['email']
        if not email:
            raise ValidationError(_("L'email est obligatoire pour un directeur."))
        return email

    def clean(self):
        cleaned = super().clean()
        pwd = cleaned.get('password')
        pwd2 = cleaned.get('password_confirm')
        if pwd and pwd2 and pwd != pwd2:
            self.add_error('password_confirm', _('Les mots de passe ne correspondent pas.'))
        return cleaned


class DirectorUpdateForm(forms.ModelForm):
    email = forms.EmailField(
        label=_('Adresse email'),
        required=False,
        widget=forms.EmailInput(attrs={'placeholder': 'directeur@ecole.ci'}),
    )
    password = forms.CharField(
        label=_('Nouveau mot de passe'),
        required=False,
        widget=forms.PasswordInput(attrs={'placeholder': 'Laisser vide pour ne pas changer'}),
        min_length=8,
        help_text=_('Laisser vide pour conserver le mot de passe actuel.'),
    )
    password_confirm = forms.CharField(
        label=_('Confirmer le mot de passe'),
        required=False,
        widget=forms.PasswordInput(attrs={'placeholder': 'Répéter le mot de passe'}),
    )

    class Meta:
        model = User
        fields = ['full_name', 'phone_number', 'email', 'is_active']
        widgets = {
            'full_name': forms.TextInput(attrs={'placeholder': 'Nom Prénom'}),
            'phone_number': forms.TextInput(attrs={'placeholder': '+225 07 00 00 00 00'}),
        }

    def clean_phone_number(self):
        phone = self.cleaned_data['phone_number']
        instance = getattr(self, 'instance', None)
        if User.objects.filter(phone_number=phone).exclude(pk=instance.pk if instance else None).exists():
            raise ValidationError(_('Ce numéro de téléphone est déjà utilisé.'))
        return phone

    def clean(self):
        cleaned = super().clean()
        pwd = cleaned.get('password')
        pwd2 = cleaned.get('password_confirm')
        if pwd or pwd2:
            if pwd != pwd2:
                self.add_error('password_confirm', _('Les mots de passe ne correspondent pas.'))
        return cleaned