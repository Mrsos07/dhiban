"""اختبار بوابة الموافقة على الشروط (بدون استدعاءات خارجية)."""
import os, sys, django
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dhiban_project.settings')
django.setup()

from whatsapp.evolution_webhook import _is_consent_text, CONSENT_WORDS

# اختبار تعرّف كلمات الموافقة
positive = ['موافق', 'موافق.', '✅ موافق', 'Ok', 'نعم', 'أكيد', 'تمام', 'أوافق']
negative = ['ابي مطعم', 'مرحبا', 'موافقتي مرفوضة', 'لا', 'شكراً']

print("== كلمات موافقة متوقعة ==")
fails = 0
for t in positive:
    res = _is_consent_text(t)
    mark = '✅' if res else '❌'
    print(f"  {mark} {t!r} → {res}")
    if not res:
        fails += 1

print("\n== كلمات ليست موافقة ==")
for t in negative:
    res = _is_consent_text(t)
    mark = '✅' if not res else '❌'
    print(f"  {mark} {t!r} → {res}")
    if res:
        fails += 1

# اختبار حقل terms_accepted على نموذج المستخدم
from users.models import WhatsAppUser
from django.utils import timezone
print("\n== نموذج WhatsAppUser: حقل terms_accepted ==")
u, _ = WhatsAppUser.objects.get_or_create(
    phone_number='+966500000999',
    defaults={'whatsapp_id': 'test_consent', 'name': 'Test Consent'},
)
print(f"  الحقل موجود: terms_accepted={u.terms_accepted} | terms_accepted_at={u.terms_accepted_at}")
u.terms_accepted = True
u.terms_accepted_at = timezone.now()
u.save(update_fields=['terms_accepted', 'terms_accepted_at'])
u.refresh_from_db()
print(f"  بعد الضبط: terms_accepted={u.terms_accepted} | at={u.terms_accepted_at}")
u.terms_accepted = False
u.terms_accepted_at = None
u.save(update_fields=['terms_accepted', 'terms_accepted_at'])

# اختبار الإعدادات
from django.conf import settings
print(f"\n== Settings ==")
print(f"  SITE_URL = {getattr(settings, 'SITE_URL', None)}")
print(f"  TERMS_URL = {getattr(settings, 'TERMS_URL', None)}")

print(f"\n== النتيجة النهائية ==")
print(f"  إخفاقات: {fails}")
sys.exit(0 if fails == 0 else 1)
