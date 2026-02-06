from django.urls import path
from .webhook import webhook_handler

app_name = 'whatsapp'

urlpatterns = [
    path('webhook/', webhook_handler, name='webhook'),
]
