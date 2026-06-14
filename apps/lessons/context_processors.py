def student_due_flashcards(request):
    """
    Nombre de flashcards dues aujourd'hui pour l'élève connecté.
    Gate sur la session élève (request.user est AnonymousUser côté élève).
    1 requête COUNT (index student/next_review_date), coût nul pour les non-élèves.
    """
    sid = request.session.get('student_id')
    if not sid:
        return {}
    try:
        from django.utils import timezone
        from apps.student_learning.models import Flashcard
        count = Flashcard.objects.filter(
            student_id=sid, next_review_date__lte=timezone.localdate(),
        ).count()
        return {'student_due_count': count}
    except Exception:
        return {'student_due_count': 0}
