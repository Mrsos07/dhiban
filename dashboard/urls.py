from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.dashboard_index, name='index'),
    
    # Suppliers
    path('suppliers/', views.suppliers_list, name='suppliers_list'),
    path('suppliers/add/', views.supplier_add, name='supplier_add'),
    path('suppliers/<uuid:pk>/edit/', views.supplier_edit, name='supplier_edit'),
    path('suppliers/<uuid:pk>/delete/', views.supplier_delete, name='supplier_delete'),
    
    # Users
    path('users/', views.users_list, name='users_list'),
    path('users/<uuid:pk>/', views.user_detail, name='user_detail'),
    
    # Conversations
    path('conversations/', views.conversations_list, name='conversations_list'),
    path('conversations/<uuid:pk>/', views.conversation_detail, name='conversation_detail'),
    
    # Categories
    path('categories/', views.categories_list, name='categories_list'),
    path('categories/add/', views.category_add, name='category_add'),
    
    # Export
    path('export/', views.export_data, name='export_data'),
    path('export/users/', views.export_users, name='export_users'),
    path('export/suppliers/', views.export_suppliers, name='export_suppliers'),
    path('export/conversations/', views.export_conversations, name='export_conversations'),
    
    # Agent
    path('agent/', views.agent_test, name='agent_test'),
    path('agent/chat/', views.agent_chat, name='agent_chat'),
    path('agent/settings/', views.agent_settings, name='agent_settings'),

    # WhatsApp Evolution API
    path('whatsapp/', views.whatsapp_connect, name='whatsapp_connect'),
    path('whatsapp/disconnect/', views.whatsapp_disconnect, name='whatsapp_disconnect'),
    path('whatsapp/status/', views.whatsapp_status_api, name='whatsapp_status'),
    path('whatsapp/set-webhook/', views.whatsapp_set_webhook, name='whatsapp_set_webhook'),
]
