import uuid
from django.db import models
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _


class WhatsAppUser(models.Model):
    """نموذج مستخدمي واتساب"""
    
    CUSTOMER_CATEGORY_CHOICES = [
        ('individual', 'فرد'),
        ('merchant', 'تاجر / صاحب محل'),
        ('restaurant', 'مطعم / كافيه'),
        ('company', 'شركة / مؤسسة'),
        ('contractor', 'مقاول / فني'),
        ('other', 'أخرى'),
    ]
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        verbose_name=_('معرف المستخدم')
    )
    
    phone_regex = RegexValidator(
        regex=r'^\+?1?\d{9,15}$',
        message=_('رقم الهاتف يجب أن يكون بالصيغة: +999999999. حتى 15 رقم مسموح.')
    )
    
    phone_number = models.CharField(
        _('رقم الهاتف'),
        validators=[phone_regex],
        max_length=17,
        unique=True,
        db_index=True
    )
    
    whatsapp_id = models.CharField(
        _('معرف واتساب'),
        max_length=50,
        unique=True,
        db_index=True
    )
    
    name = models.CharField(
        _('الاسم'),
        max_length=100,
        blank=True
    )
    
    location = models.JSONField(
        _('الموقع'),
        default=dict,
        blank=True,
        help_text=_('{"lat": 0.0, "lng": 0.0}')
    )
    
    registration_date = models.DateTimeField(
        _('تاريخ التسجيل'),
        auto_now_add=True,
        db_index=True
    )
    
    last_interaction = models.DateTimeField(
        _('آخر تفاعل'),
        auto_now=True,
        db_index=True
    )
    
    is_active = models.BooleanField(
        _('نشط'),
        default=True,
        db_index=True
    )
    
    customer_category = models.CharField(
        _('تصنيف العميل'),
        max_length=20,
        choices=CUSTOMER_CATEGORY_CHOICES,
        default='individual',
        db_index=True,
        help_text=_('تصنيف العميل لاستهداف الرسائل الدعائية')
    )
    
    tags = models.JSONField(
        _('العلامات'),
        default=list,
        blank=True,
        help_text=_('علامات مخصصة مثل: ["نشط", "قهوة", "مطعم"]')
    )
    
    preferences = models.JSONField(
        _('التفضيلات'),
        default=dict,
        blank=True,
        help_text=_('تفضيلات المستخدم مثل اللغة والإشعارات')
    )

    terms_accepted = models.BooleanField(
        _('وافق على الشروط'),
        default=False,
        db_index=True,
        help_text=_('هل ضغط المستخدم على زر الموافقة على الشروط والأحكام'),
    )

    terms_accepted_at = models.DateTimeField(
        _('تاريخ الموافقة على الشروط'),
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = _('مستخدم واتساب')
        verbose_name_plural = _('مستخدمو واتساب')
        ordering = ['-registration_date']
        indexes = [
            models.Index(fields=['phone_number', 'is_active']),
            models.Index(fields=['last_interaction']),
        ]
    
    def __str__(self):
        return f'{self.name or self.phone_number}'
    
    def get_location_display(self):
        if self.location:
            return f"({self.location.get('lat', 0)}, {self.location.get('lng', 0)})"
        return _('غير محدد')
    
    def update_last_interaction(self):
        from django.utils import timezone
        self.last_interaction = timezone.now()
        self.save(update_fields=['last_interaction'])
