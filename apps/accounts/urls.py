from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/',           views.login_view,          name='login'),
    path('logout/',          views.logout_view,         name='logout'),
    path('portal/student/',  views.portal_coming_soon,  name='portal-student'),
    path('search/',          views.search_global,       name='search-global'),
    path('switch-school/<int:school_id>/', views.switch_school, name='switch-school'),
    path('select-school/', views.select_school, name='select-school'),
]
