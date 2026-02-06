import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _


class ServiceRequest(models.Model):
    """نموذج الطلبات"""
    
    class Status(models.TextChoices):
        PENDING = 'pending', _('قيد الانتظار')
        PROCESSING = 'processing', _('قيد المعالجة')
        COMPLETED = 'completed', _('مكتمل')
        FAILED = 'failed', _('فشل')
        CANCELLED = 'cancelled', _('ملغي')
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        verbose_name=_('معرف الطلب')
    )
    
    conversation = models.ForeignKey(
        'conversations.Conversation',
        on_delete=models.CASCADE,
        related_name='requests',
        verbose_name=_('المحادثة')
    )
    
    user = models.ForeignKey(
        'users.WhatsAppUser',
        on_delete=models.CASCADE,
        related_name='requests',
        verbose_name=_('المستخدم')
    )
    
    category = models.ForeignKey(
        'suppliers.Category',
        on_delete=models.SET_NULL,
        null=True,
        related_name='requests',
        verbose_name=_('التصنيف')
    )
    
    subcategory = models.ForeignKey(
        'suppliers.SubCategory',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='requests',
        verbose_name=_('التصنيف الفرعي')
    )
    
    location_requested = models.JSONField(
        _('الموقع المطلوب'),
        default=dict,
        blank=True,
        help_text=_('{"lat": 0.0, "lng": 0.0, "address": ""}')
    )
    
    search_query = models.CharField(
        _('نص البحث'),
        max_length=500,
        blank=True
    )
    
    suppliers_suggested = models.JSONField(
        _('الموردون المقترحون'),
        default=list,
        blank=True,
        help_text=_('["supplier_id_1", "supplier_id_2"]')
    )
    
    supplier_selected = models.ForeignKey(
        'suppliers.Supplier',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='selected_requests',
        verbose_name=_('المورد المختار')
    )
    
    timestamp = models.DateTimeField(
        _('وقت الطلب'),
        auto_now_add=True,
        db_index=True
    )
    
    status = models.CharField(
        _('الحالة'),
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True
    )
    
    response_time_ms = models.PositiveIntegerField(
        _('وقت الاستجابة (مللي ثانية)'),
        null=True,
        blank=True
    )
    
    user_feedback = models.JSONField(
        _('ملاحظات المستخدم'),
        default=dict,
        blank=True,
        help_text=_('{"rating": 5, "comment": "..."}')
    )
    
    class Meta:
        verbose_name = _('طلب')
        verbose_name_plural = _('الطلبات')
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['category', 'status']),
            models.Index(fields=['status', 'timestamp']),
        ]
    
    def __str__(self):
        return f'{self.user} - {self.category} - {self.status}'
    
    def mark_completed(self):
        self.status = self.Status.COMPLETED
        self.save(update_fields=['status'])
    
    def mark_failed(self):
        self.status = self.Status.FAILED
        self.save(update_fields=['status'])
    
    def get_suggested_count(self):
        return len(self.suppliers_suggested)
