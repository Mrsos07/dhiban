"""
فحص فصل رسالة الشريك + جودة الاختيار.
"""
import os, sys, django, time, json
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dhiban_project.settings')
django.setup()

from ai_agent.agent import DhibanAgent
from ai_agent import search_context as sctx
from suppliers.models import Supplier

agent = DhibanAgent()

# 1) كم شريك عندنا فعلاً للاختبار
partner_count = Supplier.objects.filter(is_partner=True, is_active=True).count()
print(f"إجمالي الشركاء النشطين: {partner_count}")
if partner_count:
    for p in Supplier.objects.filter(is_partner=True, is_active=True)[:8]:
        sub = p.subcategory.name_ar if p.subcategory_id else '-'
        print(f"  • {p.name_ar} | تصنيف: {p.category.name_ar if p.category_id else '-'} | فرعي: {sub} | تقييم: {p.rating}")

# 2) اختبار دالة الترجيح مباشرة (بدون LLM) لعدة طلبات
print("\n" + "═" * 70)
print("اختبار find_best_partner بمدخلات مختلفة")
print("═" * 70)

cases = [
    ("مطعم", ["بيتزا"]),
    ("مطعم", ["مندي"]),
    ("مطعم", ["برجر"]),
    ("كافيه", ["هادي"]),
    ("مطعم", []),
]
for cat, specific in cases:
    print(f"\n── category={cat!r}  specific={specific}")
    partner = sctx.find_best_partner(category=cat, specific_terms=specific, user_phone='test_user')
    if partner:
        print(f"   ✅ اختار: {partner.get('name')} | category={partner.get('category')} | rating={partner.get('rating')}")
    else:
        print(f"   ❌ لا يوجد شريك مطابق (متوقع إذا لا يوجد شريك بهذا النوع)")

# 3) اختبار فصل الرسالة عبر process_message_with_history
print("\n" + "═" * 70)
print("اختبار فصل رسالة الشريك عبر الوكيل الكامل")
print("═" * 70)

test_msgs = [
    "ابي مندي",          # شريك متاح: مطعم التجربة الذهبي → متوقع list
    "ابي مطعم للعشاء",   # شريك عام متاح → متوقع list
    "ابي مطعم بيتزا",    # لا شريك بيتزا → str
]

for msg in test_msgs:
    print(f"\n── رسالة: {msg}")
    t0 = time.time()
    resp = agent.process_message_with_history(msg, [], user_id='test_user_sep')
    dt = time.time() - t0
    is_list = isinstance(resp, list)
    print(f"   النوع: {'list' if is_list else 'str'} | عدد الأجزاء: {len(resp) if is_list else 1} | زمن: {dt:.1f}ث")
    if is_list:
        for i, part in enumerate(resp):
            has_badge = 'ترشيحنا المميز' in part or 'شريك معتمد' in part
            print(f"   ── جزء {i+1} (شارة شريك: {has_badge}) ──")
            print("   " + part[:400].replace('\n', '\n   '))
    else:
        print(f"   (رسالة واحدة فقط — يعني ما فيه شريك معلّق)")
        print("   " + resp[:400].replace('\n', '\n   '))
