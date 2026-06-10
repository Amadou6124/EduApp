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
    Note, NoteSystem, NoteType,
)
from apps.students.models import Student


def round2(val):
    """Arrondi à 2 décimales, retourne Decimal."""
    if val is None:
        return None
    return Decimal(str(round(float(val), 2)))


class BulletinCalculator:
    """Calcul de moyennes et génération de bulletins."""

    # ─────────────────────────────────────────────────────────────
    # Calculs atomiques
    # ─────────────────────────────────────────────────────────────

    def calculate_subject_average(
        self,
        notes: list[Note],
        note_system: str,
        coeff_devoirs: Decimal,
        coeff_compo: Decimal,
        max_grade: Decimal,
    ) -> Optional[Decimal]:
        """
        Calcule la moyenne finale d'une matière.

        MODE DEVOIRS_COMPO :
          1. Récupérer toutes les notes de type 'devoir' (position=1)
             et la note de type 'composition' (position=2)
          2. moy_devoirs = moyenne des notes de devoir
             Si aucune → devoirs_note = 0 (non, on ignore)
             Correction : si pas de devoirs, on ne peut pas calculer.
             En pratique : si pas de devoirs saisis → None
          3. compo = note composition (unique, position=2)
             Si pas de compo → None
          4. finale = (moy_devoirs × coeff_devoirs) 
                    + (compo × coeff_compo)

          Formule standard : (devoirs × 0.4) + (compo × 0.6)

        MODE MOYENNE_SIMPLE :
          finale = sum(notes) / len(notes)

        Retourne None si pas assez de notes.
        Arrondi à 2 décimales. Jamais > max_grade.
        """
        valid_notes = [n for n in notes if n and not n.is_cancelled]
        if not valid_notes:
            return None

        if note_system == NoteSystem.DEVOIRS_COMPO:
            # Séparer devoirs (position=1) et composition (position=2)
            devoirs = [n.value for n in valid_notes if n.position == 1]
            compo   = next((n.value for n in valid_notes if n.position == 2), None)

            if not devoirs or compo is None:
                return None

            moy_devoirs = sum(devoirs) / len(devoirs)
            # Test mental : devoirs=[12,14] compo=11, coeff=(0.4,0.6)
            # moy_devoirs = 13.00
            # finale = 13 × 0.4 + 11 × 0.6 = 5.2 + 6.6 = 11.80 ✓
            finale = (moy_devoirs * coeff_devoirs) + (compo * coeff_compo)
            result = round2(finale)
            return min(result, max_grade)

        else:
            # MOYENNE_SIMPLE
            values = [n.value for n in valid_notes]
            # Test mental : notes=[15, 12, 18]
            # finale = (15+12+18)/3 = 45/3 = 15.00 ✓
            finale = sum(values) / len(values)
            result = round2(finale)
            return min(result, max_grade)

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
        total_weighted = sum(
            Decimal(str(line['weighted_grade']))
            for line in lines
            if line.get('weighted_grade') is not None
        )
        total_coeff = sum(
            Decimal(str(line['coefficient']))
            for line in lines
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
            )
            .select_related('student')
            .order_by('-general_average')
        )
        ranks = {}
        for idx, bul in enumerate(bulletins, start=1):
            ranks[bul.student_id] = idx
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

            # Moyenne matière
            avg = self.calculate_subject_average(
                cs_notes,
                cs.note_system,
                cs.coeff_devoirs,
                cs.coeff_compo,
                cs.max_grade,
            )

            # Note pondérée
            weighted = (
                self.calculate_weighted_grade(avg, cs.coefficient)
                if avg is not None
                else None
            )

            # Sous-détails pour DEVOIRS_COMPO
            devoir_avg = None
            compo_val = None
            if cs.note_system == NoteSystem.DEVOIRS_COMPO:
                devoirs = [
                    n.value for n in cs_notes
                    if n.position == 1 and not n.is_cancelled
                ]
                if devoirs:
                    devoir_avg = round2(sum(devoirs) / len(devoirs))
                compo_note = next(
                    (n for n in cs_notes if n.position == 2 and not n.is_cancelled),
                    None,
                )
                if compo_note:
                    compo_val = compo_note.value

            lines_data.append({
                'cs':            cs,
                'devoir_average': devoir_avg,
                'compo_grade':   compo_val,
                'final_average': avg,
                'weighted_grade': weighted,
                'coefficient':   cs.coefficient,
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
                appreciation = AppreciationScale.get_appreciation(
                    school, ld['final_average'],
                )
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
            bulletin.appreciation = AppreciationScale.get_appreciation(
                school, gen_avg,
            )
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
                avg = self.calculate_subject_average(
                    cs_notes, cs.note_system,
                    cs.coeff_devoirs, cs.coeff_compo, cs.max_grade,
                )
                weighted = (
                    self.calculate_weighted_grade(avg, cs.coefficient)
                    if avg is not None else None
                )

                devoir_avg = None
                compo_val = None
                if cs.note_system == NoteSystem.DEVOIRS_COMPO:
                    devoirs = [n.value for n in cs_notes if n.position == 1]
                    if devoirs:
                        devoir_avg = round2(sum(devoirs) / len(devoirs))
                    compo = next((n for n in cs_notes if n.position == 2), None)
                    if compo:
                        compo_val = compo.value

                lines_data.append({
                    'cs':              cs,
                    'devoir_average':  devoir_avg,
                    'compo_grade':     compo_val,
                    'final_average':   avg,
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
                    appr = AppreciationScale.get_appreciation(
                        school_class.school, ld['final_average'],
                    )
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
        class_size_val = len(students)
        first_avg = self.get_first_average(period, school_class)

        # Mettre à jour rangs et stats
        for bulletin in created:
            bulletin.rank = ranks.get(bulletin.student_id)
            bulletin.class_size = class_size_val
            bulletin.first_average = first_avg
            if bulletin.general_average is not None:
                bulletin.appreciation = AppreciationScale.get_appreciation(
                    school_class.school, bulletin.general_average,
                )

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