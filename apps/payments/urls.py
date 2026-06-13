from django.urls import path

from . import views

app_name = 'payments'

urlpatterns = [
    path('',                                    views.payment_dashboard,        name='dashboard'),
    path('form/<int:student_id>/',              views.payment_form,             name='form'),
    path('create/<int:student_id>/',            views.payment_create,           name='create'),
    path('student/<int:student_id>/history/',   views.payment_history,          name='history'),
    path('cancel/<int:payment_id>/',            views.payment_cancel,           name='cancel'),
    path('receipt/<int:payment_id>/',           views.payment_receipt_download, name='receipt'),
    path('receipt-preview/<int:payment_id>/',   views.receipt_preview,          name='receipt-preview'),
    path('receipt-download/<int:payment_id>/',  views.receipt_download,         name='receipt-download'),
]
