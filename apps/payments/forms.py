import datetime

from django import forms

from .models import Payment, PaymentMethod


_F = ('w-full border border-gray-300 rounded-lg px-3 py-2.5 text-sm '
      'focus:outline-none focus:ring-2 focus:ring-brand-blue '
      'text-gray-800 placeholder-gray-400')


class PaymentCreateForm(forms.ModelForm):

    class Meta:
        model = Payment
        fields = ['amount', 'payment_date', 'payment_method', 'notes']
        widgets = {
            'amount': forms.NumberInput(attrs={
                'class': _F + ' text-2xl font-bold',
                'placeholder': '0',
                'min': '1',
                'step': '1',
            }),
            'payment_date': forms.DateInput(attrs={
                'class': _F,
                'type': 'date',
            }),
            'notes': forms.Textarea(attrs={
                'class': _F,
                'rows': '2',
                'placeholder': 'Remarques optionnelles…',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['payment_date'].initial = datetime.date.today
        self.fields['payment_method'].required = True
        self.fields['notes'].required = False

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount is not None and amount <= 0:
            raise forms.ValidationError('Le montant doit être supérieur à 0 FCFA.')
        return amount


class PaymentCancelForm(forms.ModelForm):

    class Meta:
        model = Payment
        fields = ['cancellation_reason']
        widgets = {
            'cancellation_reason': forms.Textarea(attrs={
                'class': _F,
                'rows': '3',
                'placeholder': "Motif de l'annulation (obligatoire)…",
            }),
        }

    def clean_cancellation_reason(self):
        reason = self.cleaned_data.get('cancellation_reason', '').strip()
        if not reason:
            raise forms.ValidationError("Le motif d'annulation est obligatoire.")
        return reason
