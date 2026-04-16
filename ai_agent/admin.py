from django.contrib import admin
from .models import AgentSettings, PartnerPromotion


@admin.register(AgentSettings)
class AgentSettingsAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'model_name', 'temperature', 'max_tokens', 'updated_at')
    list_filter = ('is_active', 'model_name')
    search_fields = ('name',)


@admin.register(PartnerPromotion)
class PartnerPromotionAdmin(admin.ModelAdmin):
    list_display = ('partner', 'user_phone', 'context_keyword', 'was_clicked', 'created_at')
    list_filter = ('was_clicked', 'context_keyword', 'created_at')
    search_fields = ('user_phone', 'partner__name_ar', 'context_keyword', 'user_message')
    readonly_fields = ('id', 'created_at')
    date_hierarchy = 'created_at'
    list_per_page = 50
