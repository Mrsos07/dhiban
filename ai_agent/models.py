"""
نموذج إعدادات الوكيل
"""
import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _


class AgentSettings(models.Model):
    """إعدادات وكيل الذكاء الاصطناعي"""
    
    MODEL_CHOICES = [
        ('gpt-4.1', 'GPT-4.1 (الأحدث والأقوى)'),
        ('gpt-4o', 'GPT-4o (موصى به)'),
        ('gpt-4o-mini', 'GPT-4o Mini (سريع وموفر)'),
        ('gpt-4-turbo', 'GPT-4 Turbo'),
        ('gpt-3.5-turbo', 'GPT-3.5 Turbo (أرخص)'),
    ]
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    
    name = models.CharField(
        _('اسم الإعداد'),
        max_length=100,
        default='الإعداد الافتراضي'
    )
    
    is_active = models.BooleanField(
        _('نشط'),
        default=True,
        help_text=_('الإعداد النشط هو المستخدم حاليا')
    )
    
    model_name = models.CharField(
        _('نموذج الذكاء الاصطناعي'),
        max_length=50,
        choices=MODEL_CHOICES,
        default='gpt-4o'
    )
    
    system_prompt = models.TextField(
        _('System Prompt'),
        help_text=_('التعليمات الأساسية للوكيل — ملاحظة: CORE_RULES تُحقن تلقائياً فوق هذا النص ولا يمكن تجاوزها'),
        default=''  # يتم التعبئة من DHIBAN_SYSTEM_PROMPT عبر دالة get_default_prompt
    )

    @staticmethod
    def get_default_prompt():
        """إرجاع الـ prompt الافتراضي القوي من prompts.py"""
        from .prompts import DHIBAN_SYSTEM_PROMPT
        return DHIBAN_SYSTEM_PROMPT
    
    temperature = models.FloatField(
        _('Temperature'),
        default=0.9,
        help_text=_('0 = دقيق جدا 1 = إبداعي أكثر')
    )
    
    max_tokens = models.IntegerField(
        _('الحد الأقصى للكلمات'),
        default=1000
    )
    
    welcome_message = models.TextField(
        _('رسالة الترحيب'),
        default='''مرحبا! أنا ذيبان 
دليلك الذكي في عنيزة!

كيف أقدر أساعدك اليوم
- ابحث لك عن كهربائي سباك نجار...
- أدلك على أفضل المطاعم والمقاهي
- أوصلك بأي خدمة تحتاجها

فقط قل لي وش تبي! '''
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
        verbose_name = _('إعدادات الوكيل')
        verbose_name_plural = _('إعدادات الوكيل')
        ordering = ['-is_active', '-updated_at']
    
    def __str__(self):
        return f"{self.name} ({'نشط' if self.is_active else 'غير نشط'})"
    
    def save(self, *args, **kwargs):
        if self.is_active:
            AgentSettings.objects.filter(is_active=True).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)
    
    @classmethod
    def get_active(cls):
        return cls.objects.filter(is_active=True).first()


class PartnerPromotion(models.Model):
    """
    سجل ترشيحات الشركاء — يتتبع متى وأي شريك تم ترشيحه لأي مستخدم.
    يُستخدم لمنع تكرار نفس الشريك لنفس المستخدم، وتدوير الترشيحات،
    وقياس معدلات الظهور/التفاعل.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user_phone = models.CharField(
        _('رقم جوال المستخدم'),
        max_length=30,
        db_index=True,
    )

    partner = models.ForeignKey(
        'suppliers.Supplier',
        on_delete=models.CASCADE,
        related_name='promotions',
        verbose_name=_('الشريك'),
    )

    context_keyword = models.CharField(
        _('الكلمة/الفئة السياقية'),
        max_length=100,
        blank=True,
        help_text=_('الفئة أو الكلمة التي أطلقت الترشيح (مطعم، كافيه، سباك...)')
    )

    user_message = models.TextField(
        _('رسالة المستخدم'),
        blank=True,
        help_text=_('مقتطف من رسالة المستخدم التي أدّت للترشيح')
    )

    was_clicked = models.BooleanField(
        _('تم التفاعل؟'),
        default=False,
        help_text=_('هل ضغط المستخدم على الرابط أو تواصل لاحقاً؟')
    )

    created_at = models.DateTimeField(_('وقت الترشيح'), auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _('ترشيح شريك')
        verbose_name_plural = _('ترشيحات الشركاء')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user_phone', '-created_at']),
            models.Index(fields=['partner', '-created_at']),
        ]

    def __str__(self):
        return f"{self.partner.name_ar} → {self.user_phone} @ {self.created_at:%Y-%m-%d %H:%M}"
