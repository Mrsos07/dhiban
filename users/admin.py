from django.contrib import admin
from .models import WhatsAppUser


@admin.register(WhatsAppUser)
class WhatsAppUserAdmin(admin.ModelAdmin):
    list_display = ('phone_number', 'name', 'whatsapp_id', 'is_active', 'registration_date', 'last_interaction')
    list_filter = ('is_active', 'registration_date')
    search_fields = ('phone_number', 'name', 'whatsapp_id')
    readonly_fields = ('id', 'registration_date', 'last_interaction')
    ordering = ('-registration_date',)
    
    fieldsets = (
        (None, {'fields': ('id', 'phone_number', 'whatsapp_id', 'name')}),
        ('الموقع', {'fields': ('location',)}),
        ('الحالة', {'fields': ('is_active', 'preferences')}),
        ('التواريخ', {'fields': ('registration_date', 'last_interaction')}),
    )
