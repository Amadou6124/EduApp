from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import School, SchoolClass


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ('name', 'city', 'country', 'is_active', 'created_at')
    list_filter = ('is_active', 'country')
    search_fields = ('name', 'city')


@admin.register(SchoolClass)
class SchoolClassAdmin(admin.ModelAdmin):
    list_display = ('name', 'school', 'level', 'annual_fee', 'max_capacity', 'is_active')
    list_filter = ('level', 'is_active', 'school')
    search_fields = ('name', 'school__name')
    list_select_related = ('school',)
