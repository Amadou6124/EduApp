from django.urls import path

from . import views

app_name = 'payments'

urlpatterns = [
    path('',                                    views.payment_dashboard,        name='dashboard'),
    # Ancien flux d'encaissement (form/create non-alloués) supprimé au lot 6 :
    # l'unique flux est désormais finance:collect-* (allocation FIFO, lot 5).
    path('student/<int:student_id>/history/',   views.payment_history,          name='history'),
    path('cancel/<int:payment_id>/',            views.payment_cancel,           name='cancel'),
    path('receipt/<int:payment_id>/',           views.payment_receipt_download, name='receipt'),
    path('receipt-preview/<int:payment_id>/',   views.receipt_preview,          name='receipt-preview'),
    path('receipt-download/<int:payment_id>/',  views.receipt_download,         name='receipt-download'),
]
