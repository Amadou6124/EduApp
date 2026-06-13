"""
Vues Promoteur — supervision multi-écoles (cross-école, lecture seule).
Le dashboard consolidé agrège sur owned_groups → schools.
Ne PAS utiliser get_school() ici : un promoteur peut n'avoir aucune école active.
"""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.core.mixins import promoter_required


@login_required
@promoter_required
def promoter_dashboard(request):
    return render(request, 'promoter/dashboard.html', {})
