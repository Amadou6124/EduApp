"""Services gamification — XP, niveaux, badges, stats (Phase 9)."""
from django.utils import timezone


# ─── Niveaux ─────────────────────────────────────────────────────────────────

LEVEL_NAMES = {
    1: ('🌱', 'Novice'),
    2: ('📖', 'Apprenti'),
    3: ('🧠', 'Savant'),
    4: ('⭐', 'Expert'),
    5: ('🏆', 'Maître'),
}
LEVEL_DEFAULT = ('🚀', 'Génie')
XP_PER_LEVEL = 500


def level_for_xp(xp: int) -> int:
    return xp // XP_PER_LEVEL + 1


def level_info(level: int) -> tuple:
    """(emoji, nom) d'un niveau."""
    return LEVEL_NAMES.get(level, LEVEL_DEFAULT)


def xp_for_next_level(xp: int) -> int:
    """XP manquant pour le prochain niveau."""
    return level_for_xp(xp) * XP_PER_LEVEL - xp


# ─── Badges ──────────────────────────────────────────────────────────────────

BADGES_CATALOG = {
    'premiere_lecon':  {'name': 'Premier pas !',        'emoji': '🎯',     'desc': 'Première leçon complétée'},
    '5_lecons':        {'name': 'Lecteur assidu',       'emoji': '📚',     'desc': '5 leçons complétées'},
    '10_lecons':       {'name': 'Bibliothèque vivante', 'emoji': '🏛️',    'desc': '10 leçons complétées'},
    'premier_quiz':    {'name': 'Testeur',              'emoji': '✏️',     'desc': 'Premier quiz fait'},
    'quiz_parfait':    {'name': 'Perfection !',         'emoji': '💯',     'desc': 'Score parfait à un quiz'},
    '5_quiz_parfaits': {'name': 'Imbattable',           'emoji': '🏆',     'desc': '5 quiz parfaits'},
    'streak_3':        {'name': '3 jours de suite',     'emoji': '🔥',     'desc': 'Streak de 3 jours'},
    'streak_7':        {'name': 'Une semaine !',        'emoji': '🔥🔥',   'desc': 'Streak de 7 jours'},
    'streak_30':       {'name': 'Mois entier',          'emoji': '🔥🔥🔥', 'desc': 'Streak de 30 jours'},
    'niveau_3':        {'name': 'Savant',               'emoji': '🧠',     'desc': 'Niveau 3 atteint'},
    'niveau_5':        {'name': 'Maître',               'emoji': '🏆',     'desc': 'Niveau 5 atteint'},
    'niveau_6':        {'name': 'Génie !',              'emoji': '🚀',     'desc': 'Niveau 6 atteint'},
}


def _has_badge(student, badge_id: str) -> bool:
    return any(b['id'] == badge_id for b in (student.badges or []))


def check_badges(student) -> list:
    """Vérifie toutes les conditions, accorde les nouveaux badges, retourne les nouveaux."""
    from apps.student_learning.models import LessonProgress, QuizAttempt

    new_badges = []

    def grant(badge_id):
        if _has_badge(student, badge_id):
            return
        info = BADGES_CATALOG.get(badge_id, {})
        badge = {
            'id': badge_id,
            'name': info.get('name', badge_id),
            'emoji': info.get('emoji', '🎖️'),
            'earned_at': timezone.now().isoformat(),
        }
        student.badges = list(student.badges or []) + [badge]
        new_badges.append(badge)

    lessons_done = LessonProgress.objects.filter(student=student, is_completed=True).count()
    if lessons_done >= 1:  grant('premiere_lecon')
    if lessons_done >= 5:  grant('5_lecons')
    if lessons_done >= 10: grant('10_lecons')

    if QuizAttempt.objects.filter(student=student).exists():
        grant('premier_quiz')

    perfect = LessonProgress.objects.filter(student=student, quiz_bonus_awarded=True).count()
    if perfect >= 1: grant('quiz_parfait')
    if perfect >= 5: grant('5_quiz_parfaits')

    if student.streak_days >= 3:  grant('streak_3')
    if student.streak_days >= 7:  grant('streak_7')
    if student.streak_days >= 30: grant('streak_30')

    if student.current_level >= 3: grant('niveau_3')
    if student.current_level >= 5: grant('niveau_5')
    if student.current_level >= 6: grant('niveau_6')

    return new_badges


def award_xp(student, amount: int, reason: str = '') -> dict:
    """Accorde des XP, recalcule niveau + badges, sauvegarde. Retourne le résultat."""
    old_level = student.current_level
    student.total_xp += amount
    new_level = level_for_xp(student.total_xp)
    student.current_level = new_level

    new_badges = check_badges(student)
    student.save(update_fields=['total_xp', 'current_level', 'badges'])

    emoji, name = level_info(new_level)
    return {
        'xp_earned': amount,
        'new_total': student.total_xp,
        'old_level': old_level,
        'new_level': new_level,
        'leveled_up': new_level > old_level,
        'new_badges': new_badges,
        'level_emoji': emoji,
        'level_name': name,
        'xp_to_next': xp_for_next_level(student.total_xp),
        'reason': reason,
    }


def student_stats(student) -> dict:
    """Stats pour la page profil. ~5 requêtes."""
    from apps.student_learning.models import LessonProgress, QuizAttempt

    lessons_done = LessonProgress.objects.filter(student=student, is_completed=True).count()
    quiz_sessions = QuizAttempt.objects.filter(student=student).values('lesson_id').distinct().count()
    quiz_total = QuizAttempt.objects.filter(student=student).count()
    quiz_correct = QuizAttempt.objects.filter(student=student, is_correct=True).count()
    score_moyen = int(quiz_correct / quiz_total * 100) if quiz_total else 0

    emoji, name = level_info(student.current_level)
    return {
        'lessons_done': lessons_done,
        'quiz_sessions': quiz_sessions,
        'quiz_total': quiz_total,
        'score_moyen': score_moyen,
        'level_emoji': emoji,
        'level_name': name,
        'level_pct': int((student.total_xp % XP_PER_LEVEL) / XP_PER_LEVEL * 100),
        'xp_to_next': xp_for_next_level(student.total_xp),
        'badges_earned': {b['id']: b for b in (student.badges or [])},
    }
