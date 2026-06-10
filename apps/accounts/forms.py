from django import forms
from django.contrib.auth import authenticate

from .models import User

_INPUT_CLASS = (
    'w-full px-4 py-3 border border-gray-300 rounded-xl text-sm '
    'focus:outline-none focus:ring-2 focus:ring-brand-blue focus:border-brand-blue '
    'placeholder-gray-400 transition'
)


class LoginForm(forms.Form):
    phone_number = forms.CharField(
        label='Numéro de téléphone',
        max_length=20,
        widget=forms.TextInput(attrs={
            'class':        _INPUT_CLASS,
            'placeholder':  'Ex : 0700000000',
            'autocomplete': 'tel',
            'inputmode':    'tel',
            'autofocus':    True,
        }),
    )
    password = forms.CharField(
        label='Mot de passe',
        widget=forms.PasswordInput(attrs={
            'class':        _INPUT_CLASS,
            'placeholder':  '••••••••',
            'autocomplete': 'current-password',
        }),
    )

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self._user_cache = None
        super().__init__(*args, **kwargs)

    def clean(self):
        phone_number = self.cleaned_data.get('phone_number', '').strip()
        password     = self.cleaned_data.get('password', '')

        if not phone_number or not password:
            return self.cleaned_data

        # Vérifications précises avec messages distincts
        try:
            candidate = User.objects.get(phone_number=phone_number)
        except User.DoesNotExist:
            raise forms.ValidationError(
                'Aucun compte trouvé avec ce numéro de téléphone.',
                code='invalid_phone',
            )

        if not candidate.check_password(password):
            raise forms.ValidationError(
                'Mot de passe incorrect. Vérifiez et réessayez.',
                code='invalid_password',
            )

        if not candidate.is_active:
            raise forms.ValidationError(
                'Ce compte est désactivé. Contactez votre administrateur.',
                code='inactive',
            )

        # authenticate() passe par le backend pour déclencher les signaux Django
        self._user_cache = authenticate(
            self.request,
            phone_number=phone_number,
            password=password,
        )
        return self.cleaned_data

    def get_user(self):
        return self._user_cache
