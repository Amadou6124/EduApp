from django import forms

from .models import Payment


# PaymentCreateForm supprimé au lot 6 : l'ancien flux d'encaissement non-alloué
# (payment_create) n'existe plus. L'unique encaissement passe par finance:collect-create
# (allocation FIFO, lot 5). Seule subsiste l'annulation de paiement ci-dessous.
_F = ('w-full border border-gray-300 rounded-lg px-3 py-2.5 text-sm '
      'focus:outline-none focus:ring-2 focus:ring-primary-500 '
      'text-gray-800 placeholder-gray-400')


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
