from django.urls import path
from . import superadmin_views

app_name = 'superadmin'

urlpatterns = [
    # Dashboard
    path('', superadmin_views.dashboard, name='dashboard'),

    # Écoles
    path('ecoles/',                                                  superadmin_views.school_list,       name='school-list'),
    path('ecoles/create/',                                           superadmin_views.school_create,     name='school-create'),
    path('ecoles/<int:school_id>/edit/',                             superadmin_views.school_update,     name='school-update'),
    path('ecoles/<int:school_id>/toggle/',                           superadmin_views.school_toggle,     name='school-toggle'),
    path('ecoles/<int:school_id>/toggle-accounting/',                superadmin_views.accounting_toggle, name='accounting-toggle'),
    path('ecoles/<int:school_id>/director/',                         superadmin_views.director_create,   name='director-create'),
    path('ecoles/<int:school_id>/director/<int:director_id>/edit/',  superadmin_views.director_update,   name='director-update'),

    # Utilisateurs
    path('utilisateurs/',                                            superadmin_views.user_list,         name='user-list'),
    path('utilisateurs/create/',                                     superadmin_views.user_create,       name='user-create'),
    path('utilisateurs/<int:user_id>/toggle/',                       superadmin_views.user_toggle,       name='user-toggle'),
    path('utilisateurs/<int:user_id>/reset-password/',               superadmin_views.user_reset_pwd,    name='user-reset-pwd'),

    # Groupes scolaires
    path('groupes/',                                                 superadmin_views.group_list,        name='group-list'),
    path('groupes/create/',                                          superadmin_views.group_create,      name='group-create'),

    # IA & Leçons
    path('ia/',                                                      superadmin_views.ia_dashboard,      name='ia-dashboard'),
]
