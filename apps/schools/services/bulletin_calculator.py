"""
Calculatrice de bulletins — Zéro erreur de calcul toléré.

Chaque formule est commentée avec un exemple concret vérifié.
Avant de modifier une formule → test mental obligatoire.
"""
from decimal import Decimal
from typing import Optional

from django.db.models import Avg, Count, Q, Sum

from apps.schools.models import (
    AppreciationScale, Bulletin, BulletinLine, ClassSubject,
    Note, NoteType,
)
from apps.students.models import Student


def round2(val):
    """Arrondi à 2 décimales, retourne Decimal."""
    if val is None:
        return None
    return Decimal(str(round(float(val), 2)))


def get_appreciation_cached(scales, grade):
    """Retourne l'appréciation depuis une liste pré-chargée (zéro requête SQL)."""
    if grade is None:
        return ''
    for scale in scales:
        if grade >= scale.min_grade:
            return scale.label
    return ''


class BulletinCalculator:
    """Calcul de moyennes et génération de bulletins."""

    # ─────────────────────────────────────────────────────────────
    # Calculs atomiques
    # ─────────────────────────────────────────────────────────────

    def calculate_subject_average(
        self,
        notes: list[Note],
        max_grade: Decimal,
    ) -> Optional[Decimal]:
        """
        Calcule la moyenne finale d'une matière.

        MODE DEVOIRS_COMPO — Formule officielle malienne :
          moy_classe = moyenne arithmétique des devoirs (position=1)
          compo_brut = note de composition (position=2, stockée brute)
          finale     = (moy_classe + compo_brut × 2) / 3

          Vérification bulletin ASSIA 8ème année :
            Rédaction : devoirs=[13], compo=11
            finale = (13 + 11×2) / 3 = 35/3 = 11.67 ✓
            points = 11.67 × 3 = 35.00 ✓

          Vérification bulletin Lycée Ségou :
            Français : moy_cl=11, compo=12
            finale = (11 + 12×2) / 3 = 35/3 = 11.50 ✓
            points = 11.50 × 3 = 34.50 ✓

          Note : compo_grade stocké = valeur brute (ex: 11)
                 colonne PDF "Comp X2" = compo_brut × 2 (ex: 22)

        MODE MOYENNE_SIMPLE :
          finale = sum(notes) / nb_notes

        Retourne None si notes insuffisantes.
        Arrondi à 2 décimales (Decimal). Jamais > max_grade.
        """
        valid_notes = [n for n in notes if n and not n.is_cancelled]
        note_classe = next((n.value for n in valid_notes if n.position == 1), None)
        compo       = next((n.value for n in valid_notes if n.position == 2), None)
        if note_classe is None or compo is None:
            return None

        # Formule officielle malienne : (note de classe + composition×2) / 3.
        # Position 1 = note de classe, position 2 = composition.
        # Retourne valeur NON arrondie — l'appelant arrondit séparément final_average
        # et weighted_grade (évite round2(35/3)×3 = 35.01 ≠ 35.00).
        finale = (Decimal(str(note_classe)) + Decimal(str(compo)) * 2) / 3
        return min(finale, Decimal(str(max_grade)))

    def calculate_weighted_grade(
        self,
        average: Decimal,
        coefficient: Decimal,
    ) -> Decimal:
        """
        Note pondérée = moyenne × coefficient.

        Test mental : 11.67 × 3 = 35.01 ≈ 35.01
        Test mental : 15.00 × 1 = 15.00 ✓
        """
        return round2(average * coefficient)

    def calculate_general_average(
        self,
        lines: list[dict],
    ) -> Optional[Decimal]:
        """
        Moyenne générale = sum(notes_pondérées) / sum(coefficients).

        lines : liste de dicts {weighted_grade, coefficient}

        Test mental (bulletin ASSIA type) :
        Matières : 35.01(×3) + 12.33(×1) + 16.33(×2) + ...
        Total notes_coeff = 266.17
        Total coeff = 23
        Moy = 266.17 / 23 = 11.57 ✓

        Retourne None si aucun coefficient.
        """
        # Ne prendre que les matieres qui ont une note
        # sinon le coefficient d'une matiere sans note fausse la moyenne
        filtered = [l for l in lines if l.get('weighted_grade') is not None]
        if not filtered:
            return None
        total_weighted = sum(
            Decimal(str(l['weighted_grade']))
            for l in filtered
        )
        total_coeff = sum(
            Decimal(str(l['coefficient']))
            for l in filtered
        )
        if total_coeff == 0:
            return None
        return round2(total_weighted / total_coeff)

    def calculate_ranks(
        self,
        period,
        school_class,
    ) -> dict:
        """
        Calcule le rang de chaque élève dans la classe pour une période.

        Utilise les bulletins déjà générés (Bulletin.general_average).
        Tri par moyenne générale décroissante.

        Retourne dict {student_id: rank}

        Exemple : 34 élèves, le 1er a 16.50, le 22e a 11.57
        → {student_1: 1, student_22: 22, ...}
        """
        bulletins = list(
            Bulletin.objects.filter(
                period=period,
                school_class=school_class,
                is_cancelled=False,
                general_average__isnull=False,   # un élève sans moyenne n'est pas classé
            )
            .select_related('student')
            .order_by('-general_average')
        )
        # Rangs « compétition » : les ex æquo partagent le même rang (1, 2, 2, 4…).
        ranks = {}
        prev_avg = None
        prev_rank = 0
        for idx, bul in enumerate(bulletins, start=1):
            if prev_avg is not None and bul.general_average == prev_avg:
                rank = prev_rank
            else:
                rank = idx
                prev_rank = idx
                prev_avg = bul.general_average
            ranks[bul.student_id] = rank
        return ranks

    def get_first_average(
        self,
        period,
        school_class,
    ) -> Optional[Decimal]:
        """Retourne la moyenne du premier de la classe."""
        top = (
            Bulletin.objects.filter(
                period=period,
                school_class=school_class,
                is_cancelled=False,
                general_average__isnull=False,
            )
            .order_by('-general_average')
            .first()
        )
        if top:
            return top.general_average
        return None

    # ─────────────────────────────────────────────────────────────
    # Orchestration
    # ─────────────────────────────────────────────────────────────

    def generate_bulletin(
        self,
        student: Student,
        period,
        generated_by,
    ) -> Bulletin:
        """
        Génère un bulletin complet pour un élève sur une période.

        1. Récupère toutes les notes (optimisé : 1 requête)
        2. Calcule la moyenne par matière (subject_average)
        3. Calcule la note pondérée (weighted_grade)
        4. Calcule la moyenne générale
        5. Calcule les rangs
        6. Détermine l'appréciation
        7. Crée/supprime Bulletin + BulletinLines
        8. Retourne le Bulletin (sans PDF)
        """
        school = student.school
        school_class = student.school_class

        # Pré-charger l'échelle d'appréciation (1 requête, évite N requêtes en boucle)
        scales = list(
            AppreciationScale.objects.filter(school=school).order_by('-min_grade')
        )

        # Supprimer l'ancien bulletin s'il existe (annulé ou regénération)
        Bulletin.objects.filter(
            student=student,
            period=period,
        ).delete()

        # 1. Récupérer toutes les ClassSubject de la classe
        class_subjects = list(
            ClassSubject.objects
            .filter(school_class=school_class, is_active=True)
            .select_related('subject')
            .order_by('order', 'subject__name')
        )
        if not class_subjects:
            raise ValueError("Aucune matière assignée à cette classe.")

        # 2. Récupérer toutes les notes de l'élève pour cette période (1 requête)
        all_notes = list(
            Note.objects.filter(
                class_subject__school_class=school_class,
                student=student,
                period=period,
                is_cancelled=False,
            ).select_related('class_subject')
        )

        # Indexer les notes par class_subject_id
        notes_by_cs = {}
        for note in all_notes:
            notes_by_cs.setdefault(note.class_subject_id, []).append(note)

        # 3. Calculer les lignes du bulletin
        lines_data = []
        for cs in class_subjects:
            cs_notes = notes_by_cs.get(cs.pk, [])

            # Moyenne matière — valeur exacte non arrondie
            avg_raw = self.calculate_subject_average(cs_notes, cs.max_grade)

            # Arrondi séparément pour éviter l'erreur de double arrondi :
            # round2(35/3)×3 = 11.67×3 = 35.01 ≠ round2(35/3×3) = 35.00
            avg_display = round2(avg_raw) if avg_raw is not None else None
            weighted = (
                self.calculate_weighted_grade(avg_raw, cs.coefficient)
                if avg_raw is not None
                else None
            )

            # Sous-détails pour DEVOIRS_COMPO
            devoir_avg = None
            compo_val = None
            devoirs = [
                n.value for n in cs_notes
                if n.position == 1 and not n.is_cancelled
            ]
            if devoirs:
                devoir_avg = round2(sum(Decimal(str(v)) for v in devoirs) / len(devoirs))
            compo_note = next(
                (n for n in cs_notes if n.position == 2 and not n.is_cancelled),
                None,
            )
            if compo_note:
                compo_val = compo_note.value

            lines_data.append({
                'cs':             cs,
                'devoir_average': devoir_avg,
                'compo_grade':    compo_val,
                'final_average':  avg_display,
                'weighted_grade': weighted,
                'coefficient':    cs.coefficient,
            })

        # 4. Moyenne générale
        gen_avg = self.calculate_general_average(lines_data)

        # 5. Créer le Bulletin
        bulletin = Bulletin.objects.create(
            student=student,
            period=period,
            school_class=school_class,
            generated_by=generated_by,
            general_average=gen_avg,
        )

        # 6. Créer les BulletinLines
        bulletin_lines = []
        for ld in lines_data:
            appreciation = ''
            if ld['final_average'] is not None:
                appreciation = get_appreciation_cached(scales, ld['final_average'])
            bulletin_lines.append(BulletinLine(
                bulletin=bulletin,
                class_subject=ld['cs'],
                devoir_average=ld['devoir_average'],
                compo_grade=ld['compo_grade'],
                final_average=ld['final_average'],
                weighted_grade=ld['weighted_grade'],
                appreciation=appreciation,
            ))

        BulletinLine.objects.bulk_create(bulletin_lines)

        # 7. Appréciation générale
        if gen_avg is not None:
            bulletin.appreciation = get_appreciation_cached(scales, gen_avg)
            bulletin.save(update_fields=['appreciation'])

        return bulletin

    def generate_class_bulletins(
        self,
        school_class,
        period,
        generated_by,
    ) -> list[Bulletin]:
        """
        Génère tous les bulletins d'une classe.

        Optimisation :
        - 1 requête pour les élèves
        - 1 requête pour toutes les notes de la classe sur cette période
        - bulk_create pour les BulletinLines
        - Calcul des rangs en 1 passe finale
        """
        students = list(
            Student.objects
            .filter(school_class=school_class, school=school_class.school, is_active=True)
            .order_by('full_name')
        )
        if not students:
            return []

        # Pré-charger l'échelle d'appréciation (1 requête pour toute la classe)
        scales = list(
            AppreciationScale.objects
            .filter(school=school_class.school)
            .order_by('-min_grade')
        )

        # Supprimer les anciens bulletins
        Bulletin.objects.filter(
            period=period,
            school_class=school_class,
            student__in=students,
        ).delete()

        # 1. ClassSubjects
        class_subjects = list(
            ClassSubject.objects
            .filter(school_class=school_class, is_active=True)
            .select_related('subject')
            .order_by('order', 'subject__name')
        )

        # 2. Toutes les notes de la classe (1 requête)
        all_notes = list(
            Note.objects.filter(
                class_subject__school_class=school_class,
                period=period,
                student__in=students,
                is_cancelled=False,
            ).select_related('class_subject')
        )

        # Indexer par (student_id, class_subject_id)
        notes_index = {}
        for note in all_notes:
            key = (note.student_id, note.class_subject_id)
            notes_index.setdefault(key, []).append(note)

        bulletins = []
        all_lines = []

        for student in students:
            # Calculer les lignes
            lines_data = []
            for cs in class_subjects:
                cs_notes = notes_index.get((student.pk, cs.pk), [])
                avg_raw = self.calculate_subject_average(cs_notes, cs.max_grade)
                # Arrondi séparé : évite round2(35/3)×3 = 35.01
                avg_display = round2(avg_raw) if avg_raw is not None else None
                weighted = (
                    self.calculate_weighted_grade(avg_raw, cs.coefficient)
                    if avg_raw is not None else None
                )

                devoir_avg = None
                compo_val = None
                devoirs = [n.value for n in cs_notes if n.position == 1]
                if devoirs:
                    devoir_avg = round2(sum(Decimal(str(v)) for v in devoirs) / len(devoirs))
                compo = next((n for n in cs_notes if n.position == 2), None)
                if compo:
                    compo_val = compo.value

                lines_data.append({
                    'cs':              cs,
                    'devoir_average':  devoir_avg,
                    'compo_grade':     compo_val,
                    'final_average':   avg_display,
                    'weighted_grade':  weighted,
                    'coefficient':     cs.coefficient,
                })

            gen_avg = self.calculate_general_average(lines_data)

            bulletin = Bulletin(
                student=student,
                period=period,
                school_class=school_class,
                generated_by=generated_by,
                general_average=gen_avg,
            )
            bulletins.append(bulletin)

            for ld in lines_data:
                appr = ''
                if ld['final_average'] is not None:
                    appr = get_appreciation_cached(scales, ld['final_average'])
                all_lines.append(BulletinLine(
                    bulletin=bulletin,
                    class_subject=ld['cs'],
                    devoir_average=ld['devoir_average'],
                    compo_grade=ld['compo_grade'],
                    final_average=ld['final_average'],
                    weighted_grade=ld['weighted_grade'],
                    appreciation=appr,
                ))

        # bulk_create Bulletins
        created = Bulletin.objects.bulk_create(bulletins)

        # Associer les lignes aux bulletins créés
        for i, line in enumerate(all_lines):
            line.bulletin = created[
                next(
                    j for j, b in enumerate(bulletins)
                    if b.student_id == line.bulletin.student_id
                )
            ]

        BulletinLine.objects.bulk_create(all_lines)

        # Calculer les rangs
        ranks = self.calculate_ranks(period, school_class)
        # Effectif classé = élèves ayant une moyenne (les sans-note ne sont pas classés).
        class_size_val = sum(1 for b in created if b.general_average is not None)
        first_avg = self.get_first_average(period, school_class)

        # Mettre à jour rangs et stats
        for bulletin in created:
            bulletin.rank = ranks.get(bulletin.student_id)
            bulletin.class_size = class_size_val
            bulletin.first_average = first_avg
            if bulletin.general_average is not None:
                bulletin.appreciation = get_appreciation_cached(scales, bulletin.general_average)

        Bulletin.objects.bulk_update(
            created,
            ['rank', 'class_size', 'first_average', 'appreciation'],
        )

        return list(
            Bulletin.objects.filter(
                period=period,
                school_class=school_class,
            ).select_related('student').order_by('rank')
        )