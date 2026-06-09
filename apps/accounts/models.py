from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils.translation import gettext_lazy as _


class UserRole(models.TextChoices):
    DIRECTOR = 'director', _('Directeur')
    STAFF = 'staff', _('Staff / Secrétaire')
    TEACHER = 'teacher', _('Professeur')
    STUDENT = 'student', _('Élève')
    PARENT = 'parent', _('Parent')


class UserManager(BaseUserManager):

    def create_user(self, phone_number, password=None, **extra_fields):
        if not phone_number:
            raise ValueError(_('Le numéro de téléphone est obligatoire'))
        user = self.model(phone_number=phone_number, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone_number, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', UserRole.DIRECTOR)
        return self.create_user(phone_number, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    # Identifiant principal : numéro de téléphone
    phone_number = models.CharField(
        _('numéro de téléphone'),
        max_length=20,
        unique=True,
    )
    email = models.EmailField(_('adresse email'), blank=True)
    full_name = models.CharField(_('nom complet'), max_length=150)
    role = models.CharField(
        _('rôle'),
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.STAFF,
    )
    # Lien vers l'école pour l'isolation multi-tenant
    school = models.ForeignKey(
        'schools.School',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='users',
        verbose_name=_('école'),
    )
    is_active = models.BooleanField(_('actif'), default=True)
    is_staff = models.BooleanField(_('membre du staff Django'), default=False)
    created_at = models.DateTimeField(_('créé le'), auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = 'phone_number'
    REQUIRED_FIELDS = ['full_name']

    class Meta:
        verbose_name = _('utilisateur')
        verbose_name_plural = _('utilisateurs')

    def __str__(self):
        return f'{self.full_name} ({self.get_role_display()})'
