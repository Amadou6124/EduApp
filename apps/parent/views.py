"""
Vues Espace Parent — cross-école, lecture seule.
Données via request.user.guarded_students. Ne JAMAIS appeler get_school().
"""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.core.mixins import parent_required


@login_required
@parent_required
def parent_dashboard(request):
    return render(request, 'parent/dashboard.html', {})
