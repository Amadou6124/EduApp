import random
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _


def generate_student_access_code():
    """Génère un code d'accès à 6 chiffres. L'unicité par école est garantie par unique_together."""
    return str(random.randint(100000, 999999))


def generate_matricule(school, year=None):
    """Prochain matricule pour cette école : format ``AAAA-NNNN``.

    Séquence propre à chaque école, remise à zéro chaque année (l'année étant déjà
    dans le matricule). Immuable une fois attribué. L'unicité par école est garantie
    par la contrainte ``uniq_matricule_per_school`` ; ce compteur ne fait que proposer
    le prochain numéro libre (échelle pilote : génération une à une).
    """
    from django.utils import timezone
    year = year or timezone.now().year
    prefix = f'{year}-'
    max_seq = 0
    for m in (Student.objects
              .filter(school=school, matricule__startswith=prefix)
              .values_list('matricule', flat=True)):
        try:
            max_seq = max(max_seq, int(m.rsplit('-', 1)[-1]))
        except (ValueError, IndexError):
            continue
    return f'{prefix}{max_seq + 1:04d}'


def split_full_name(full_name):
    """Découpe « Prénom Nom » (au mieux) → (first_name, last_name).

    Convention d'affichage de l'app : le prénom vient en premier. Utilisé par les chemins
    qui ne fournissent qu'un nom complet (import en masse, seeds hérités). Approximatif
    par nature — l'inscription unitaire, elle, saisit Nom et Prénom séparément.
    """
    parts = (full_name or '').split()
    if len(parts) >= 2:
        return parts[0], ' '.join(parts[1:])
    if parts:
        return '', parts[0]
    return '', ''


class ParentRelationship(models.TextChoices):
    FATHER   = 'father',   _('Père')
    MOTHER   = 'mother',   _('Mère')
    GUARDIAN = 'guardian', _('Tuteur/Tutrice')
    OTHER    = 'other',    _('Autre')


class Gender(models.TextChoices):
    # Valeurs stockées volontairement courtes ('M'/'F') et stables : elles serviront
    # de clé pour sélectionner automatiquement la variante de tarif « tenue »
    # (uniforme fille / garçon) dans le module Finances. Ne pas renommer les codes.
    MALE   = 'M', _('Garçon')
    FEMALE = 'F', _('Fille')


class Student(models.Model):
    school = models.ForeignKey(
        'schools.School',
        on_delete=models.PROTECT,
        related_name='students',
        verbose_name=_('école'),
    )
    school_class = models.ForeignKey(
        'schools.SchoolClass',
        on_delete=models.PROTECT,
        related_name='students',
        verbose_name=_('classe'),
    )
    # ── Identité ──────────────────────────────────────────────────────────
    # Nom de famille et prénom(s) SÉPARÉS = la source de vérité de l'identité
    # (registre alphabétique par nom, documents officiels, correspondance état civil).
    # blank=True : certains chemins hérités (seeds) ne passent que full_name ; save()
    # les dérive alors au mieux. Le formulaire d'inscription, lui, les rend obligatoires.
    last_name  = models.CharField(_('nom de famille'), max_length=100, blank=True, db_index=True)
    first_name = models.CharField(_('prénom(s)'), max_length=100, blank=True)

    # full_name — ⚠️ NE PAS SUPPRIMER, NE PAS SAISIR À LA MAIN. Ce n'est PAS du code mort :
    # c'est un champ DÉRIVÉ, recomposé automatiquement dans save() à partir de « Prénom Nom ».
    # On le garde STOCKÉ (et non calculé à la volée en @property) parce que le tri par défaut,
    # la recherche, l'index base de données et ~70 affichages en dépendent — or une base ne
    # peut ni trier ni filtrer sur une simple property Python. C'est donc un cache d'affichage
    # cohérent (mis à jour à chaque save), la seule saisie réelle étant last_name + first_name.
    full_name = models.CharField(_('nom complet (auto)'), max_length=200, db_index=True)

    date_of_birth = models.DateField(_('date de naissance'), null=True, blank=True)
    birth_place   = models.CharField(_('lieu de naissance'), max_length=120, blank=True)

    # Matricule administratif, immuable, unique par école. Généré dans save() (format
    # AAAA-NNNN, séquence par école remise à zéro chaque année) mais MODIFIABLE : le directeur
    # peut y saisir le matricule officiel. Ce n'est PAS un identifiant de connexion — il est
    # public (imprimé sur les documents). Voir docs/decision-authentification.md.
    matricule = models.CharField(_('matricule'), max_length=20, blank=True, db_index=True)
    # Genre — additif : null/blank car les élèves déjà inscrits n'ont pas cette donnée.
    # Pilote l'application automatique du tarif de tenue (variante fille/garçon) à
    # l'inscription ; tant qu'il est null, aucune variante genrée n'est appliquée.
    gender = models.CharField(
        _('genre'),
        max_length=1,
        choices=Gender.choices,
        null=True,
        blank=True,
    )
    # Les responsables (père, mère, tuteur…) sont désormais la SEULE source des contacts :
    # voir StudentGuardian (couche « responsable » = info + accès portail optionnel).
    # Code à 6 chiffres, unique par école (contrainte unique_together dans Meta)
    access_code = models.CharField(
        _('code d\'accès'),
        max_length=6,
        default=generate_student_access_code,
        editable=False,
    )
    # Frais copiés de la classe au moment de l'inscription
    tuition_fee = models.DecimalField(
        _('frais de scolarité (FCFA)'),
        max_digits=10,
        decimal_places=0,
    )
    notes = models.TextField(_('informations supplémentaires'), blank=True)
    # ⚠️ NE JAMAIS écrire `student.is_active = True/False` directement. Ce flag est un CACHE
    # de l'état de scolarité, qui doit rester cohérent avec le statut de l'inscription
    # (StudentEnrollment.status). Les deux se mutent ENSEMBLE, uniquement via Student.archive()
    # et Student.reactivate() (atomiques). Toute mutation directe rouvre le bug de dérive
    # (flag ≠ statut) — cf. le crash d'archivage réparé. Voir aussi docs/roadmap-post-demo.md.
    is_active = models.BooleanField(_('actif'), default=True)
    enrolled_at = models.DateTimeField(_('inscrit le'), auto_now_add=True)
    updated_at = models.DateTimeField(_('modifié le'), auto_now=True)

    # ── Auth portail élève (session isolée — voir apps/core/student_auth.py) ──
    password = models.CharField(
        _('mot de passe'), max_length=128, blank=True,
        help_text=_('Hash du mot de passe élève'),
    )
    last_login = models.DateTimeField(_('dernière connexion'), null=True, blank=True)

    # ── Gamification ──────────────────────────────────────────────────
    total_xp           = models.PositiveIntegerField(_('XP total'), default=0)
    current_level      = models.PositiveSmallIntegerField(_('niveau'), default=1)
    streak_days        = models.PositiveSmallIntegerField(_('streak jours'), default=0)
    last_activity_date = models.DateField(_('dernière activité'), null=True, blank=True)
    longest_streak     = models.PositiveSmallIntegerField(_('meilleur streak'), default=0)
    badges             = models.JSONField(_('badges'), default=list)

    class Meta:
        verbose_name = _('élève')
        verbose_name_plural = _('élèves')
        # Registre classé par nom de famille (convention scolaire), puis prénom.
        ordering = ['last_name', 'first_name']
        # Code d'accès unique au sein d'une école
        unique_together = [('school', 'access_code')]
        constraints = [
            # Matricule unique par école (uniquement quand renseigné).
            models.UniqueConstraint(
                fields=['school', 'matricule'],
                condition=models.Q(matricule__gt=''),
                name='uniq_matricule_per_school',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'school_class'], name='student_school_class_idx'),
            models.Index(fields=['school', 'is_active'],    name='student_school_active_idx'),
        ]

    def __str__(self):
        return f'{self.full_name} — {self.school_class.name}'

    def save(self, *args, **kwargs):
        # full_name est DÉRIVÉ (voir le commentaire du champ) : on le recompose ici à partir
        # de Prénom + Nom pour garantir sa cohérence partout où il est affiché et trié.
        first = (self.first_name or '').strip()
        last  = (self.last_name or '').strip()
        composed = f'{first} {last}'.strip()
        if composed:
            self.full_name = composed
        elif self.full_name:
            # Chemin hérité (seed/import ne passant que full_name) : on préserve full_name et
            # on dérive au mieux Prénom/Nom pour ne pas laisser l'identité séparée vide.
            first, last = split_full_name(self.full_name)
            self.first_name = self.first_name or first
            self.last_name  = self.last_name or last

        # Matricule : attribué une seule fois puis immuable (généré s'il est absent).
        if not self.matricule and self.school_id:
            self.matricule = generate_matricule(self.school)

        super().save(*args, **kwargs)

    # ── Méthodes financières ──────────────────────────────────────────────
    # Utilisent self.payments.all() pour bénéficier du prefetch_related cache.
    # Dans les vues de liste, préfetcher avec :
    #   .prefetch_related('payments')
    # Aucune requête supplémentaire ne sera émise.

    def get_total_paid(self):
        return sum(p.amount for p in self.payments.all() if not p.is_cancelled)

    def get_balance_due(self):
        return self.tuition_fee - self.get_total_paid()

    def get_payment_status(self):
        paid = self.get_total_paid()
        if paid >= self.tuition_fee:
            return 'paid'
        if paid > 0:
            return 'partial'
        return 'unpaid'

    def has_parent_linked(self):
        return self.guardians.exists()

    def get_avatar_colors(self):
        """Retourne (bg, text) selon la première lettre du nom (A-E/F-J/K-O/P-T/U-Z)."""
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

    def get_initials(self):
        parts = self.full_name.split()
        if len(parts) >= 2:
            return f'{parts[0][0]}{parts[-1][0]}'.upper()
        return self.full_name[:2].upper() if self.full_name else '??'

    # ── Auth portail élève ────────────────────────────────────────────────
    def set_student_password(self, raw):
        from django.contrib.auth.hashers import make_password
        self.password = make_password(raw)

    def check_student_password(self, raw):
        from django.contrib.auth.hashers import check_password
        return bool(self.password) and check_password(raw, self.password)

    # ── Cycle de vie : archivage / réactivation ───────────────────────────────
    # SEUL point autorisé à toucher is_active. Ces 2 méthodes changent le flag ET le statut
    # de l'inscription ENSEMBLE, atomiquement → impossible que le flag et le statut divergent
    # (la cause du bug d'archivage : is_active muté à la main, indépendamment de l'inscription).
    def archive(self, status, ended_at=None):
        """Archive l'élève : l'inscription ACTIVE (année active) passe au `status` donné
        (transféré / diplômé / retiré) + `ended_at`, et is_active=False. On ne CRÉE jamais
        d'inscription (une seule par élève et par année → on mute son statut). Idempotent."""
        from django.utils import timezone
        ended_at = ended_at or timezone.now().date()
        with transaction.atomic():
            enr = (
                self.enrollments.filter(status=EnrollmentStatus.ACTIVE)
                .order_by('-school_year__start_date').first()
            )
            if enr is not None:
                enr.status = status
                enr.ended_at = ended_at
                enr.save(update_fields=['status', 'ended_at'])
            if self.is_active:
                self.is_active = False
                self.save(update_fields=['is_active'])

    def reactivate(self):
        """Annule un retrait : l'inscription archivée la plus récente repasse ACTIVE +
        is_active=True. REFUSÉ si elle est GRADUATED (diplômé = terminal : un retour se fait
        par une NOUVELLE inscription, pas une réactivation). Retourne True si réactivé, sinon
        False. Idempotent."""
        with transaction.atomic():
            enr = (
                self.enrollments.exclude(status=EnrollmentStatus.ACTIVE)
                .order_by('-school_year__start_date', '-created_at').first()
            )
            if enr is not None and enr.status == EnrollmentStatus.GRADUATED:
                return False
            if enr is not None:
                enr.status = EnrollmentStatus.ACTIVE
                enr.ended_at = None
                enr.save(update_fields=['status', 'ended_at'])
            if not self.is_active:
                self.is_active = True
                self.save(update_fields=['is_active'])
            return True


class StudentGuardian(models.Model):
    """
    Responsable d'un élève (père, mère, tuteur/tutrice…).

    Deux couches en un seul modèle :
      - INFO (toujours) : full_name, phone, email, relationship, is_primary. C'est le
        contact du dossier — il n'exige AUCUN compte.
      - ACCÈS PORTAIL (optionnel) : si `guardian` (User) est renseigné, ce responsable
        peut se connecter au portail parent. Sinon (guardian=NULL) = info seule.

    La résolution des enfants côté portail (apps/parent/children.py) filtre guardian=user :
    les responsables info-seule en sont donc naturellement exclus.
    """
    guardian = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE, null=True, blank=True,
        related_name='guarded_students', verbose_name=_('compte portail (optionnel)'),
    )
    student = models.ForeignKey(
        'Student', on_delete=models.CASCADE,
        related_name='guardians', verbose_name=_('élève'),
    )
    full_name = models.CharField(_('nom du responsable'), max_length=200, blank=True)
    phone     = models.CharField(_('téléphone'), max_length=20, blank=True)
    relationship = models.CharField(
        _('lien de parenté'), max_length=10,
        choices=ParentRelationship.choices, blank=True,
    )
    is_primary = models.BooleanField(_('contact principal'), default=False)
    created_at = models.DateTimeField(_('créé le'), auto_now_add=True)

    @property
    def display_name(self):
        """Nom à afficher : celui du responsable, sinon celui du compte lié."""
        return self.full_name or (self.guardian.full_name if self.guardian_id else '')

    @property
    def display_phone(self):
        return self.phone or (self.guardian.phone_number if self.guardian_id else '')

    @property
    def has_portal_access(self):
        return self.guardian_id is not None

    class Meta:
        verbose_name = _('parent d\'élève')
        verbose_name_plural = _('parents d\'élèves')
        constraints = [
            models.UniqueConstraint(
                fields=['guardian', 'student'], name='unique_guardian_student',
            ),
        ]
        indexes = [
            models.Index(fields=['guardian'], name='guardian_idx'),
            models.Index(fields=['student'],  name='guardian_student_idx'),
        ]

    def __str__(self):
        return f'{self.display_name or "?"} → {self.student.full_name}'


class EnrollmentStatus(models.TextChoices):
    ACTIVE      = 'active',      _('En cours')
    TRANSFERRED = 'transferred', _('Transféré')
    GRADUATED   = 'graduated',   _('Diplômé / Passé')
    WITHDRAWN   = 'withdrawn',   _('Retiré')


class StudentEnrollment(models.Model):
    """
    Source de vérité de l'inscription d'un élève, année scolaire par année scolaire.

    Contrat de données (module Finances, à partir du lot 1) :
      - L'enrollment de statut ACTIVE rattaché à l'année active de l'école
        (SchoolYear.is_active=True) EST l'inscription courante de l'élève.
      - Student.school_class reste la classe courante en lecture rapide (cache de
        l'enrollment ACTIVE) le temps de cette transition ; les deux doivent rester
        cohérents. À terme, les frais de l'année s'accrocheront à l'enrollment, pas
        au Student.
      - Un transfert / une fin d'année fige l'enrollment (status TRANSFERRED /
        GRADUATED / WITHDRAWN, ended_at renseigné) : il devient une archive en
        lecture seule. Le passage de classe (lot 7) créera l'enrollment de N+1.

    Note : school_year est nullable pour préserver les archives historiques créées
    avant ce lot (retraits enregistrés sans année active) — voir la contrainte
    d'unicité conditionnelle ci-dessous.
    """
    student = models.ForeignKey(
        'Student', on_delete=models.PROTECT,
        related_name='enrollments', verbose_name=_('élève'),
    )
    school = models.ForeignKey(
        'schools.School', on_delete=models.PROTECT,
        related_name='enrollments', verbose_name=_('école'),
    )
    school_class = models.ForeignKey(
        'schools.SchoolClass', on_delete=models.PROTECT,
        related_name='enrollments', verbose_name=_('classe'),
    )
    school_year = models.ForeignKey(
        'schools.SchoolYear', on_delete=models.PROTECT,
        related_name='enrollments', verbose_name=_('année scolaire'),
        null=True, blank=True,
    )
    status = models.CharField(
        _('statut'), max_length=20,
        choices=EnrollmentStatus.choices, default=EnrollmentStatus.ACTIVE,
    )
    enrolled_at = models.DateField(_('inscrit le'), null=True, blank=True)
    ended_at    = models.DateField(_('terminé le'), null=True, blank=True)
    created_at  = models.DateTimeField(_('créé le'), auto_now_add=True)

    class Meta:
        verbose_name = _('inscription')
        verbose_name_plural = _('inscriptions')
        ordering = ['-created_at']
        constraints = [
            # Un seul enrollment par couple (élève, année scolaire).
            # Condition school_year__isnull=False : la contrainte ne s'applique QUE
            # lorsqu'une année est renseignée. Les archives historiques sans année
            # (school_year=NULL, créées avant le lot 1) ne sont donc jamais bloquées,
            # et plusieurs d'entre elles peuvent coexister pour un même élève.
            models.UniqueConstraint(
                fields=['student', 'school_year'],
                condition=models.Q(school_year__isnull=False),
                name='uniq_enrollment_student_year',
            ),
        ]
        indexes = [
            models.Index(fields=['student', 'status'],    name='enrollment_student_status_idx'),
            models.Index(fields=['school', 'school_year'], name='enrollment_school_year_idx'),
        ]

    def __str__(self):
        return f'{self.student.full_name} @ {self.school.name} [{self.get_status_display()}]'
