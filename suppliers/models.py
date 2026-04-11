import uuid
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.postgres.fields import ArrayField
from django.utils.translation import gettext_lazy as _


class Category(models.Model):
    """نموذج التصنيفات"""
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    
    name_ar = models.CharField(
        _('الاسم بالعربية'),
        max_length=100,
        unique=True
    )
    
    name_en = models.CharField(
        _('الاسم بالإنجليزية'),
        max_length=100,
        blank=True
    )
    
    icon = models.CharField(
        _('الأيقونة'),
        max_length=50,
        blank=True,
        help_text=_('اسم أيقونة Bootstrap Icons')
    )
    
    is_active = models.BooleanField(
        _('نشط'),
        default=True
    )
    
    order = models.PositiveIntegerField(
        _('الترتيب'),
        default=0
    )
    
    class Meta:
        verbose_name = _('تصنيف')
        verbose_name_plural = _('التصنيفات')
        ordering = ['order', 'name_ar']
    
    def __str__(self):
        return self.name_ar


class SubCategory(models.Model):
    """نموذج التصنيفات الفرعية"""
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name='subcategories',
        verbose_name=_('التصنيف الرئيسي')
    )
    
    name_ar = models.CharField(
        _('الاسم بالعربية'),
        max_length=100
    )
    
    name_en = models.CharField(
        _('الاسم بالإنجليزية'),
        max_length=100,
        blank=True
    )
    
    is_active = models.BooleanField(
        _('نشط'),
        default=True
    )
    
    class Meta:
        verbose_name = _('تصنيف فرعي')
        verbose_name_plural = _('التصنيفات الفرعية')
        ordering = ['category', 'name_ar']
        unique_together = ['category', 'name_ar']
    
    def __str__(self):
        return f'{self.category.name_ar} - {self.name_ar}'


class Supplier(models.Model):
    """نموذج الموردين"""
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        verbose_name=_('معرف المورد')
    )
    
    name_ar = models.CharField(
        _('الاسم بالعربية'),
        max_length=200,
        db_index=True
    )
    
    name_en = models.CharField(
        _('الاسم بالإنجليزية'),
        max_length=200,
        blank=True
    )
    
    description = models.TextField(
        _('الوصف'),
        blank=True
    )
    
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name='suppliers',
        verbose_name=_('التصنيف')
    )
    
    subcategory = models.ForeignKey(
        SubCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='suppliers',
        verbose_name=_('التصنيف الفرعي')
    )
    
    # الموقع الجغرافي (JSON بدلاً من PostGIS للتبسيط)
    location = models.JSONField(
        _('الموقع'),
        default=dict,
        help_text=_('{"lat": 0.0, "lng": 0.0, "address": ""}')
    )
    
    google_maps_place_id = models.CharField(
        _('معرف Google Maps'),
        max_length=100,
        blank=True,
        db_index=True
    )
    
    google_maps_url = models.URLField(
        _('رابط Google Maps'),
        max_length=500,
        blank=True,
        help_text=_('رابط الموقع على خرائط جوجل')
    )
    
    # أرقام الهواتف (JSON Array)
    phone_numbers = models.JSONField(
        _('أرقام الهواتف'),
        default=list,
        help_text=_('["0501234567", "0551234567"]')
    )
    
    email = models.EmailField(
        _('البريد الإلكتروني'),
        blank=True
    )
    
    website = models.URLField(
        _('الموقع الإلكتروني'),
        blank=True
    )
    
    rating = models.DecimalField(
        _('التقييم'),
        max_digits=3,
        decimal_places=2,
        default=0.00,
        validators=[MinValueValidator(0), MaxValueValidator(5)]
    )
    
    reviews_count = models.PositiveIntegerField(
        _('عدد التقييمات'),
        default=0
    )
    
    is_partner = models.BooleanField(
        _('شريك'),
        default=False,
        db_index=True,
        help_text=_('هل المورد شريك رسمي؟')
    )
    
    is_verified = models.BooleanField(
        _('موثق'),
        default=False,
        db_index=True
    )
    
    is_active = models.BooleanField(
        _('نشط'),
        default=True,
        db_index=True
    )
    
    agent_notes = models.TextField(
        _('ملاحظات الوكيل'),
        blank=True,
        help_text=_('ملاحظات خاصة يقرأها الوكيل عند اقتراح هذا المحل (مثال: متخصص في وجبات عائلية، يوفر توصيل)')
    )
    
    working_hours = models.JSONField(
        _('ساعات العمل'),
        default=dict,
        blank=True,
        help_text=_('{"saturday": {"open": "08:00", "close": "22:00"}, ...}')
    )
    
    services = models.JSONField(
        _('الخدمات'),
        default=list,
        blank=True,
        help_text=_('["خدمة 1", "خدمة 2"]')
    )
    
    images = models.JSONField(
        _('الصور'),
        default=list,
        blank=True,
        help_text=_('["url1", "url2"]')
    )
    
    created_at = models.DateTimeField(
        _('تاريخ الإنشاء'),
        auto_now_add=True
    )
    
    updated_at = models.DateTimeField(
        _('تاريخ التحديث'),
        auto_now=True
    )
    
    class Meta:
        verbose_name = _('مورد')
        verbose_name_plural = _('الموردون')
        ordering = ['-is_partner', '-rating', 'name_ar']
        indexes = [
            models.Index(fields=['category', 'is_active']),
            models.Index(fields=['is_partner', 'is_active']),
            models.Index(fields=['rating']),
            models.Index(fields=['name_ar']),
        ]
    
    def __str__(self):
        return self.name_ar
    
    def get_primary_phone(self):
        if self.phone_numbers:
            return self.phone_numbers[0]
        return None
    
    def get_location_display(self):
        if self.location:
            return self.location.get('address', f"({self.location.get('lat', 0)}, {self.location.get('lng', 0)})")
        return _('غير محدد')


class Partner(Supplier):
    """
    Proxy model للشركاء المعتمدين — يعرض فقط is_partner=True.
    لا يحتاج migration — يستخدم نفس جدول Supplier.
    """
    class Meta:
        proxy = True
        verbose_name = _('شريك معتمد')
        verbose_name_plural = _('الشركاء المعتمدون')

    def save(self, *args, **kwargs):
        self.is_partner = True
        super().save(*args, **kwargs)
