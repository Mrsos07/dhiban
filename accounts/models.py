from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _


class CustomUserManager(BaseUserManager):
    """مدير مخصص للمستخدمين يدعم تسجيل الدخول بالبريد الإلكتروني"""
    
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError(_('البريد الإلكتروني مطلوب'))
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('role', 'super_admin')
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('المستخدم الخارق يجب أن يكون is_staff=True'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('المستخدم الخارق يجب أن يكون is_superuser=True'))
        
        return self.create_user(email, password, **extra_fields)


class CustomUser(AbstractUser):
    """نموذج مستخدم مخصص مع حقول إضافية ونظام أدوار"""
    
    class Role(models.TextChoices):
        SUPER_ADMIN = 'super_admin', _('مدير عام')
        ADMIN = 'admin', _('مدير')
        MODERATOR = 'moderator', _('مشرف')
    
    username = None
    email = models.EmailField(_('البريد الإلكتروني'), unique=True)
    phone_number = models.CharField(_('رقم الجوال'), max_length=20, blank=True, null=True)
    role = models.CharField(
        _('الدور'),
        max_length=20,
        choices=Role.choices,
        default=Role.MODERATOR
    )
    created_at = models.DateTimeField(_('تاريخ الإنشاء'), auto_now_add=True)
    updated_at = models.DateTimeField(_('تاريخ التحديث'), auto_now=True)
    failed_login_attempts = models.PositiveIntegerField(_('محاولات الدخول الفاشلة'), default=0)
    last_failed_login = models.DateTimeField(_('آخر محاولة فاشلة'), null=True, blank=True)
    is_locked = models.BooleanField(_('الحساب مقفل'), default=False)
    locked_until = models.DateTimeField(_('مقفل حتى'), null=True, blank=True)
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']
    
    objects = CustomUserManager()
    
    class Meta:
        verbose_name = _('مستخدم')
        verbose_name_plural = _('المستخدمون')
        ordering = ['-created_at']
    
    def __str__(self):
        return self.email
    
    def get_full_name(self):
        return f'{self.first_name} {self.last_name}'.strip() or self.email
    
    def is_super_admin(self):
        return self.role == self.Role.SUPER_ADMIN
    
    def is_admin(self):
        return self.role in [self.Role.SUPER_ADMIN, self.Role.ADMIN]
    
    def is_moderator(self):
        return self.role in [self.Role.SUPER_ADMIN, self.Role.ADMIN, self.Role.MODERATOR]
    
    def reset_failed_attempts(self):
        self.failed_login_attempts = 0
        self.last_failed_login = None
        self.is_locked = False
        self.locked_until = None
        self.save(update_fields=['failed_login_attempts', 'last_failed_login', 'is_locked', 'locked_until'])


class LoginAttempt(models.Model):
    """نموذج لتسجيل محاولات الدخول"""
    
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='login_attempts',
        verbose_name=_('المستخدم')
    )
    email = models.EmailField(_('البريد الإلكتروني'))
    ip_address = models.GenericIPAddressField(_('عنوان IP'))
    user_agent = models.TextField(_('معلومات المتصفح'), blank=True)
    successful = models.BooleanField(_('ناجحة'), default=False)
    timestamp = models.DateTimeField(_('الوقت'), auto_now_add=True)
    failure_reason = models.CharField(_('سبب الفشل'), max_length=100, blank=True)
    
    class Meta:
        verbose_name = _('محاولة دخول')
        verbose_name_plural = _('محاولات الدخول')
        ordering = ['-timestamp']
    
    def __str__(self):
        status = 'ناجحة' if self.successful else 'فاشلة'
        return f'{self.email} - {status} - {self.timestamp}'
