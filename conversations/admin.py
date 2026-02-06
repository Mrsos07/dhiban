from django.contrib import admin
from .models import Conversation


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('user', 'intent_detected', 'resolved', 'started_at', 'ended_at', 'get_messages_count')
    list_filter = ('intent_detected', 'resolved', 'started_at')
    search_fields = ('user__phone_number', 'user__name')
    readonly_fields = ('id', 'started_at')
    ordering = ('-started_at',)
    
    fieldsets = (
        (None, {'fields': ('id', 'user')}),
        ('المحادثة', {'fields': ('messages', 'intent_detected', 'sentiment_score')}),
        ('الحالة', {'fields': ('resolved', 'notes')}),
        ('التواريخ', {'fields': ('started_at', 'ended_at')}),
    )
    
    def get_messages_count(self, obj):
        return obj.get_messages_count()
    get_messages_count.short_description = 'عدد الرسائل'
