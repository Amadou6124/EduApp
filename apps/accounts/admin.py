from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('phone_number', 'full_name', 'role', 'school', 'is_active')
    list_filter = ('role', 'is_active', 'school')
    search_fields = ('phone_number', 'full_name', 'email')
    ordering = ('full_name',)

    fieldsets = (
        (None, {'fields': ('phone_number', 'password')}),
        (_('Informations personnelles'), {'fields': ('full_name', 'email')}),
        (_('Rôle & école'), {'fields': ('role', 'school')}),
        (_('Permissions'), {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('phone_number', 'full_name', 'role', 'school', 'password1', 'password2'),
        }),
    )
