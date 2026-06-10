from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('receipt_number', 'student', 'amount', 'payment_method', 'payment_date', 'collected_by', 'is_cancelled')
    list_filter = ('payment_method', 'is_cancelled', 'payment_date')
    search_fields = ('receipt_number', 'student__full_name')
    readonly_fields = ('receipt_number', 'created_at')
    list_select_related = ('student', 'collected_by')
