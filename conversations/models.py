import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _


class Conversation(models.Model):
    """نموذج المحادثات"""
    
    class Intent(models.TextChoices):
        SEARCH = 'search', _('بحث')
        INQUIRY = 'inquiry', _('استفسار')
        COMPLAINT = 'complaint', _('شكوى')
        FEEDBACK = 'feedback', _('ملاحظات')
        BOOKING = 'booking', _('حجز')
        OTHER = 'other', _('أخرى')
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        verbose_name=_('معرف المحادثة')
    )
    
    user = models.ForeignKey(
        'users.WhatsAppUser',
        on_delete=models.CASCADE,
        related_name='conversations',
        verbose_name=_('المستخدم')
    )
    
    started_at = models.DateTimeField(
        _('بداية المحادثة'),
        auto_now_add=True,
        db_index=True
    )
    
    ended_at = models.DateTimeField(
        _('نهاية المحادثة'),
        null=True,
        blank=True
    )
    
    messages = models.JSONField(
        _('الرسائل'),
        default=list,
        help_text=_('[{"role": "user/bot", "content": "...", "timestamp": "..."}]')
    )
    
    intent_detected = models.CharField(
        _('النية المكتشفة'),
        max_length=20,
        choices=Intent.choices,
        default=Intent.OTHER,
        db_index=True
    )
    
    sentiment_score = models.DecimalField(
        _('درجة المشاعر'),
        max_digits=4,
        decimal_places=3,
        default=0.000,
        help_text=_('-1.0 سلبي إلى 1.0 إيجابي')
    )
    
    resolved = models.BooleanField(
        _('تم الحل'),
        default=False,
        db_index=True
    )
    
    notes = models.TextField(
        _('ملاحظات'),
        blank=True
    )
    
    class Meta:
        verbose_name = _('محادثة')
        verbose_name_plural = _('المحادثات')
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['user', 'started_at']),
            models.Index(fields=['intent_detected', 'resolved']),
        ]
    
    def __str__(self):
        return f'{self.user} - {self.started_at.strftime("%Y-%m-%d %H:%M")}'
    
    def add_message(self, role, content):
        from django.utils import timezone
        message = {
            'role': role,
            'content': content,
            'timestamp': timezone.now().isoformat()
        }
        self.messages.append(message)
        self.save(update_fields=['messages'])
    
    def end_conversation(self):
        from django.utils import timezone
        self.ended_at = timezone.now()
        self.save(update_fields=['ended_at'])
    
    def get_messages_count(self):
        return len(self.messages)
    
    def get_duration(self):
        if self.ended_at:
            return self.ended_at - self.started_at
        return None
