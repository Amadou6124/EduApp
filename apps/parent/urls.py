from django.urls import path

from . import views

app_name = 'parent'

urlpatterns = [
    path('', views.parent_dashboard, name='dashboard'),
    path('bulletins/', views.parent_bulletins, name='bulletins'),
    path('payments/', views.parent_payments, name='payments'),
    path('account/', views.parent_account, name='account'),
    path('scolarite/', views.parent_scolarite, name='scolarite'),
    path('notes/', views.parent_notes, name='notes'),
    path('suivi/', views.parent_suivi, name='suivi'),
    path('annonces/', views.parent_annonces, name='annonces'),
    path('bulletin/<int:bulletin_id>/pdf/', views.parent_bulletin_pdf, name='bulletin-pdf'),
    path('notifications/', views.parent_notifications, name='notifications'),
    path('notifications/<int:notif_id>/open/', views.notification_open, name='notif-open'),
    path('notifications/<int:notif_id>/delete/', views.notification_delete, name='notif-delete'),
    path('notifications/read-all/', views.notifications_read_all, name='notif-read-all'),
    path('notifications/clear/', views.notifications_clear, name='notif-clear'),
]
