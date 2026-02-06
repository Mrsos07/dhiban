from django.contrib import admin
from .models import ServiceRequest


@admin.register(ServiceRequest)
class ServiceRequestAdmin(admin.ModelAdmin):
    list_display = ('user', 'category', 'status', 'timestamp', 'response_time_ms')
    list_filter = ('status', 'category', 'timestamp')
    search_fields = ('user__phone_number', 'search_query')
    readonly_fields = ('id', 'timestamp')
    ordering = ('-timestamp',)
    
    fieldsets = (
        (None, {'fields': ('id', 'conversation', 'user')}),
        ('الطلب', {'fields': ('category', 'subcategory', 'search_query', 'location_requested')}),
        ('النتائج', {'fields': ('suppliers_suggested', 'supplier_selected')}),
        ('الحالة', {'fields': ('status', 'response_time_ms')}),
        ('الملاحظات', {'fields': ('user_feedback',)}),
        ('التواريخ', {'fields': ('timestamp',)}),
    )
