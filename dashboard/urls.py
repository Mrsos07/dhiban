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
    
    # Partners
    path('partners/', views.partners_list, name='partners_list'),
    path('partners/add/', views.partner_add, name='partner_add'),
    path('partners/<uuid:pk>/edit/', views.partner_edit, name='partner_edit'),
    path('partners/<uuid:pk>/delete/', views.partner_delete, name='partner_delete'),

    # API
    path('api/subcategories/', views.get_subcategories_api, name='api_subcategories'),

    # Users
    path('users/', views.users_list, name='users_list'),
    path('users/<uuid:pk>/', views.user_detail, name='user_detail'),
    
    # Conversations
    path('conversations/', views.conversations_list, name='conversations_list'),
    path('conversations/<uuid:pk>/', views.conversation_detail, name='conversation_detail'),
    
    # Categories
    path('categories/', views.categories_list, name='categories_list'),
    path('categories/add/', views.category_add, name='category_add'),
    path('categories/<uuid:pk>/edit/', views.category_edit, name='category_edit'),
    path('categories/<uuid:pk>/delete/', views.category_delete, name='category_delete'),

    # Subcategories
    path('subcategories/add/', views.subcategory_add, name='subcategory_add'),
    path('subcategories/<uuid:pk>/edit/', views.subcategory_edit, name='subcategory_edit'),
    path('subcategories/<uuid:pk>/delete/', views.subcategory_delete, name='subcategory_delete'),
    
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
    
    # Diagnostics
    path('diag/test-vision/', views.diag_test_vision, name='diag_test_vision'),
]
