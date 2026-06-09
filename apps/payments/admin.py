from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('receipt_number', 'student', 'amount', 'payment_method', 'collected_by', 'paid_at', 'is_valid')
    list_filter = ('payment_method', 'is_valid', 'paid_at')
    search_fields = ('receipt_number', 'student__full_name')
    readonly_fields = ('receipt_number', 'paid_at')
    list_select_related = ('student', 'collected_by')
