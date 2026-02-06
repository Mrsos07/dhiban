"""
نموذج إعدادات الوكيل
"""
import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _


class AgentSettings(models.Model):
    """إعدادات وكيل الذكاء الاصطناعي"""
    
    MODEL_CHOICES = [
        ('gpt-4o-mini', 'GPT-4o Mini (سريع وموفر)'),
        ('gpt-4o', 'GPT-4o (أقوى)'),
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
        default='gpt-4o-mini'
    )
    
    system_prompt = models.TextField(
        _('System Prompt'),
        help_text=_('التعليمات الأساسية للوكيل'),
        default='''أنت "ذيبان"  - وكيل ذكاء اصطناعي ودليل ذكي لمدينة عنيزة في منطقة القصيم بالمملكة العربية السعودية.

## مهمتك:
- مساعدة المستخدمين في إيجاد أفضل الخدمات والأماكن في عنيزة
- فهم طلبات المستخدمين بلغتهم الطبيعية
- البحث في قاعدة بيانات الموردين وتقديم أفضل الخيارات
- الرد بطريقة ودية ومختصرة

## قواعد الرد:
1. رد دائما باللغة العربية
2. كن مختصرا ومفيدا
3. استخدم الإيموجي بشكل معتدل
4. قدم معلومات التواصل عند توفرها
5. إذا لم تجد نتائج اقترح بدائل أو اطلب توضيحا

تذكر: أنت ذيبان الذئب الذكي الذي يعرف كل شيء عن عنيزة! '''
    )
    
    temperature = models.FloatField(
        _('Temperature'),
        default=0.7,
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
