from django.urls import path
from . import views

urlpatterns = [
    path('', views.landing_page, name='landing'),
    path('admin-login/', views.admin_login, name='admin_login'),
]
