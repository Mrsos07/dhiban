from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('admin-login/', views.admin_login_view, name='admin_login'),
    path('admin-logout/', views.admin_logout_view, name='admin_logout'),
]
