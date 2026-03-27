from django.urls import path
from .webhook import webhook_handler
from .evolution_webhook import evolution_webhook_handler

app_name = 'whatsapp'

urlpatterns = [
    path('webhook/', webhook_handler, name='webhook'),
    path('evolution/webhook/', evolution_webhook_handler, name='evolution_webhook'),
]
