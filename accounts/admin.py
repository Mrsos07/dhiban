from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _
from .models import CustomUser, LoginAttempt


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    """إدارة المستخدمين المخصصة"""
    
    list_display = ('email', 'first_name', 'last_name', 'role', 'is_active', 'is_staff', 'created_at')
    list_filter = ('role', 'is_active', 'is_staff', 'is_superuser', 'created_at')
    search_fields = ('email', 'first_name', 'last_name', 'phone_number')
    ordering = ('-created_at',)
    
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('المعلومات الشخصية'), {'fields': ('first_name', 'last_name', 'phone_number')}),
        (_('الصلاحيات'), {'fields': ('role', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        (_('الأمان'), {'fields': ('failed_login_attempts', 'is_locked', 'locked_until')}),
        (_('التواريخ المهمة'), {'fields': ('last_login', 'created_at', 'updated_at')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'first_name', 'last_name', 'phone_number', 'role', 'password1', 'password2'),
        }),
    )
    
    readonly_fields = ('created_at', 'updated_at', 'last_login')


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    """إدارة محاولات الدخول"""
    
    list_display = ('email', 'ip_address', 'successful', 'timestamp', 'failure_reason')
    list_filter = ('successful', 'timestamp')
    search_fields = ('email', 'ip_address')
    ordering = ('-timestamp',)
    readonly_fields = ('user', 'email', 'ip_address', 'user_agent', 'successful', 'timestamp', 'failure_reason')
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
