from django.urls import path
from . import views

urlpatterns = [
    path('', views.landing_page, name='landing'),
    path('admin-login/', views.admin_login, name='admin_login'),
    path('branding/logo-png', views.serve_logo, {'filename': 'logo.png'}, name='logo_png'),
    path('branding/logo-svg', views.serve_logo, {'filename': 'logo.svg'}, name='logo_svg'),
]
