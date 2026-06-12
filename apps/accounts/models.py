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
    # Titre affiché dans l'interface (ex : Censeur, Comptable, Surveillant)
    job_title = models.CharField(
        _('titre du poste'),
        max_length=100,
        blank=True,
        help_text=_('Ex : Censeur, Comptable, Surveillant'),
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

    def get_full_name(self):
        return self.full_name

    def get_short_name(self):
        parts = self.full_name.split()
        return parts[0] if parts else self.phone_number

    def get_initials(self):
        parts = self.full_name.split()
        if len(parts) >= 2:
            return f'{parts[0][0]}{parts[-1][0]}'.upper()
        return self.full_name[:2].upper() if self.full_name else '??'

    def get_avatar_colors(self):
        """Retourne (bg, text) selon la première lettre du nom — cohérent avec Student."""
        letter = self.full_name[0].upper() if self.full_name else 'A'
        if letter <= 'E':
            return '#E6F1FB', '#0C447C'
        if letter <= 'J':
            return '#EAF3DE', '#27500A'
        if letter <= 'O':
            return '#FAEEDA', '#633806'
        if letter <= 'T':
            return '#EEEDFE', '#3C3489'
        return '#FAECE7', '#712B13'


class StaffPermission(models.Model):
    """
    Permissions granulaires pour les membres staff d'une école.
    Un directeur configure ces permissions individuellement.
    Chaque utilisateur staff a au plus un enregistrement (OneToOne).
    """
    user = models.OneToOneField(
        User,
        on_delete=models.PROTECT,
        related_name='staff_permission',
        verbose_name=_('utilisateur'),
    )

    # ── Paiements ─────────────────────────────────────────────────
    can_view_payments   = models.BooleanField(_('voir les paiements'),        default=False)
    can_create_payments = models.BooleanField(_('enregistrer des paiements'), default=False)
    can_cancel_payments = models.BooleanField(_('annuler des paiements'),     default=False)

    # ── Élèves ────────────────────────────────────────────────────
    can_view_students   = models.BooleanField(_('voir les élèves'),     default=True)
    can_create_students = models.BooleanField(_('inscrire des élèves'), default=False)
    can_edit_students   = models.BooleanField(_('modifier les fiches'), default=False)

    # ── Notes ─────────────────────────────────────────────────────
    can_view_notes = models.BooleanField(_('voir les notes'),              default=False)
    can_edit_notes = models.BooleanField(_('saisir / modifier les notes'), default=False)

    # ── Bulletins ─────────────────────────────────────────────────
    can_generate_bulletins = models.BooleanField(_('générer les bulletins'),     default=False)
    can_download_bulletins = models.BooleanField(_('télécharger les bulletins'), default=False)

    # ── Absences ──────────────────────────────────────────────────
    can_record_absences = models.BooleanField(_('enregistrer les absences'), default=False)

    # ── Classes ───────────────────────────────────────────────────
    can_view_classes = models.BooleanField(_('voir les classes'),     default=True)
    can_edit_classes = models.BooleanField(_('modifier les classes'), default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('permission staff')
        verbose_name_plural = _('permissions staff')

    def __str__(self):
        return f'Permissions de {self.user.full_name}'

    # ── Profils prédéfinis ────────────────────────────────────────

    @classmethod
    def preset_comptable(cls, user):
        return cls.objects.create(
            user=user,
            can_view_payments=True,
            can_create_payments=True,
            can_cancel_payments=False,
            can_view_students=True,
        )

    @classmethod
    def preset_censeur(cls, user):
        return cls.objects.create(
            user=user,
            can_view_students=True,
            can_view_notes=True,
            can_edit_notes=True,
            can_generate_bulletins=True,
            can_download_bulletins=True,
            can_record_absences=True,
            can_view_classes=True,
        )

    @classmethod
    def preset_surveillant(cls, user):
        return cls.objects.create(
            user=user,
            can_view_students=True,
            can_record_absences=True,
        )

    @classmethod
    def preset_informaticien(cls, user):
        return cls.objects.create(
            user=user,
            can_view_notes=True,
            can_generate_bulletins=True,
            can_download_bulletins=True,
            can_view_students=True,
            can_view_classes=True,
        )

    @classmethod
    def preset_secretaire(cls, user):
        return cls.objects.create(
            user=user,
            can_view_students=True,
            can_create_students=True,
            can_edit_students=True,
            can_view_payments=True,
            can_create_payments=True,
            can_view_classes=True,
        )
