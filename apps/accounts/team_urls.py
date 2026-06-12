from django.urls import path

from . import team_views

app_name = 'team'

urlpatterns = [
    path('',                              team_views.team_list,                name='list'),
    path('create/',                       team_views.team_member_create,       name='create'),
    path('<int:user_id>/',                team_views.team_member_detail,       name='detail'),
    path('<int:user_id>/edit/',           team_views.team_member_edit,         name='edit'),
    path('<int:user_id>/permissions/',    team_views.team_permissions_update,  name='permissions'),
    path('<int:user_id>/deactivate/',     team_views.team_member_deactivate,   name='deactivate'),
    path('<int:user_id>/subjects/',       team_views.teacher_subjects_update,  name='subjects'),
]
