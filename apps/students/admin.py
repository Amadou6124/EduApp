from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import Student


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'school_class', 'school', 'access_code', 'get_payment_status', 'enrolled_at')
    list_filter = ('school_class__level', 'school', 'is_active')
    search_fields = ('full_name', 'access_code', 'phone_number', 'parent_phone_number')
    readonly_fields = ('access_code', 'enrolled_at', 'updated_at')
    list_select_related = ('school_class', 'school')

    @admin.display(description=_('Statut paiement'))
    def get_payment_status(self, obj):
        status_map = {'paid': '✅ Soldé', 'partial': '⏳ Partiel', 'unpaid': '❌ Non payé'}
        return status_map.get(obj.get_payment_status(), '—')
