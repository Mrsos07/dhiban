from django.urls import path, re_path
from . import views

urlpatterns = [
    path('', views.landing_page, name='landing'),
    path('admin-login/', views.admin_login, name='admin_login'),
    re_path(r'^(?P<filename>logo\.png|logo\.svg)$', views.serve_logo, name='serve_logo'),
]
