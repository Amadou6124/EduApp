"""Boucle de retour — Phase 5 : rendre au prof les résultats des élèves sur ses leçons.

Signal-leçon SÉPARÉ (Option A) : plus riche que la note (par concept), il ne se
fond PAS dans la moyenne par matière du Suivi (pas de mapping texte hasardeux) —
il vit comme son propre indicateur.

Fonctions pures de lecture (aucune écriture) :
  lesson_cohort(lesson)              → élèves attendus (classes déployées)
  student_lesson_mastery(s, lesson)  → 0..1 (meilleur examen, sinon précision quiz)
  lesson_results(lesson)             → résumé classe + par élève
  concept_breakdown(lesson)          → taux de réussite par concept
  strugglers(lesson, threshold)      → élèves sous le seuil (le « signal »)
"""
from django.db.models import Count, Q

from .models import LessonDeployment
from apps.student_learning.models import QuizAttempt, ExamAttempt
from apps.students.models import Student


def lesson_cohort(lesson):
    """Élèves attendus = élèves actifs des classes où la leçon est déployée (active)."""
    class_ids = list(
        LessonDeployment.objects
        .filter(lesson=lesson, is_active=True)
        .values_list('school_class_id', flat=True)
    )
    return Student.objects.filter(
        school_class_id__in=class_ids, is_active=True).distinct()


def _best_exam_by_student(lesson):
    """{student_id: meilleure ExamAttempt} (score le plus haut, puis la plus récente)."""
    best = {}
    for att in (ExamAttempt.objects.filter(lesson=lesson)
                .order_by('student_id', '-score', '-started_at')):
        if att.student_id not in best:      # 1re rencontrée par élève = meilleure
            best[att.student_id] = att
    return best


def _quiz_accuracy_by_student(lesson):
    """{student_id: {total, correct}} sur les quiz de la leçon."""
    return {
        r['student_id']: r
        for r in (QuizAttempt.objects.filter(lesson=lesson)
                  .values('student_id')
                  .annotate(total=Count('id'), correct=Count('id', filter=Q(is_correct=True))))
    }


def student_lesson_mastery(student, lesson):
    """Maîtrise 0..1 : meilleur score d'examen, sinon précision aux quiz, sinon None."""
    best = (ExamAttempt.objects.filter(lesson=lesson, student=student)
            .order_by('-score').values_list('score', flat=True).first())
    if best is not None:
        return round(best, 2)
    agg = QuizAttempt.objects.filter(lesson=lesson, student=student).aggregate(
        total=Count('id'), correct=Count('id', filter=Q(is_correct=True)))
    if agg['total']:
        return round(agg['correct'] / agg['total'], 2)
    return None


def lesson_results(lesson):
    """Résumé classe + par élève, pour la fiche « Résultats » du prof."""
    cohort = list(lesson_cohort(lesson))
    best_exam = _best_exam_by_student(lesson)
    quiz_by_student = _quiz_accuracy_by_student(lesson)

    students, started, passed, exam_scores = [], 0, 0, []
    for s in cohort:
        ex = best_exam.get(s.pk)
        qz = quiz_by_student.get(s.pk)
        has_activity = ex is not None or qz is not None
        if has_activity:
            started += 1
        if ex and ex.passed:
            passed += 1
        if ex:
            exam_scores.append(ex.score)
        students.append({
            'student':       s,
            'started':       has_activity,
            'exam_score':    round(ex.score, 2) if ex else None,
            'exam_passed':   ex.passed if ex else None,
            'quiz_accuracy': (round(qz['correct'] / qz['total'], 2)
                              if qz and qz['total'] else None),
        })
    return {
        'cohort':         len(cohort),
        'started':        started,
        'not_started':    len(cohort) - started,
        'passed':         passed,
        'avg_exam_score': round(sum(exam_scores) / len(exam_scores), 2) if exam_scores else None,
        'students':       students,
    }


def concept_breakdown(lesson):
    """Taux de réussite PAR CONCEPT (depuis la meilleure tentative d'examen de chaque
    élève ; chaque réponse porte son concept_id en snapshot)."""
    tally = {}   # concept_id -> [correct, total]
    for att in _best_exam_by_student(lesson).values():
        for ans in (att.answers or []):
            if not isinstance(ans, dict):
                continue
            cid = ans.get('concept_id')
            if not cid:
                continue
            t = tally.setdefault(cid, [0, 0])
            t[1] += 1
            if ans.get('is_correct'):
                t[0] += 1
    return [
        {'concept_id': cid, 'correct': c, 'total': tot,
         'rate': round(c / tot, 2) if tot else None}
        for cid, (c, tot) in tally.items()
    ]


def strugglers(lesson, threshold=0.5):
    """Signal séparé (Option A) : élèves ayant travaillé mais sous le seuil de maîtrise."""
    out = []
    for row in lesson_results(lesson)['students']:
        if not row['started']:
            continue
        mastery = row['exam_score'] if row['exam_score'] is not None else row['quiz_accuracy']
        if mastery is not None and mastery < threshold:
            out.append({'student': row['student'], 'mastery': mastery})
    return out
