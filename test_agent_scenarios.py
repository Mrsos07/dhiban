"""
اختبار الوكيل بسيناريوهات متعددة لكشف النتائج الوهمية
يستدعي process_message_with_history مباشرة (نفس ما يستخدمه الواتساب)
"""
import os
import sys
import django

# Fix Windows encoding
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dhiban_project.settings')
django.setup()

from ai_agent.agent import DhibanAgent

agent = DhibanAgent()

SCENARIOS = [
    {
        "name": "1. طلب مطعم مباشر",
        "message": "ابي مطعم مندي في عنيزة",
        "history": [],
    },
    {
        "name": "2. طلب كافيه",
        "message": "وين أحسن كافيه في عنيزة؟",
        "history": [],
    },
    {
        "name": "3. طلب خدمة كهربائي",
        "message": "ابي كهربائي الحين",
        "history": [],
    },
    {
        "name": "4. طلب صيدلية",
        "message": "وين أقرب صيدلية؟",
        "history": [],
    },
    {
        "name": "5. طلب خطة يومية",
        "message": "ابي خطة يومية مع العيلة",
        "history": [
            {"role": "assistant", "content": "هلا يالغالي! خطة يومية شي حلو 😊 وش تحبون: أكل وتمشية ولا تبي تضيف كافيه وحلويات؟"},
            {"role": "user", "content": "أكل وتمشية وكافيه"},
        ],
    },
    {
        "name": "6. سؤال مبهم (المفروض يسأل لا يبحث)",
        "message": "ابي اطلع اليوم",
        "history": [],
    },
    {
        "name": "7. نتائج غير موجودة (مطعم نادر)",
        "message": "ابي مطعم سوشي في عنيزة",
        "history": [],
    },
]

print("=" * 70)
print("اختبار الوكيل - كشف النتائج الوهمية")
print("=" * 70)

HALLUCINATION_KEYWORDS = [
    "برياني", "الذهبي", "الأصيل", "الفاخر", "النخبة", "الراقي",
    "مطعم ", "كافيه ", "صيدلية ", "ورشة "
]

for scenario in SCENARIOS:
    print(f"\n{'─'*70}")
    print(f"📋 {scenario['name']}")
    print(f"💬 الرسالة: {scenario['message']}")
    if scenario['history']:
        print(f"📜 التاريخ: {len(scenario['history'])} رسائل سابقة")
    print()

    try:
        response = agent.process_message_with_history(
            user_message=scenario['message'],
            chat_history=scenario['history']
        )
        print(f"🤖 الرد:\n{response}")

        # فحص هل استخدم أداة أم لا (بسيط - نشوف هل النتيجة فيها بيانات حقيقية)
        has_maps_url = "maps.google" in response or "google.com/maps" in response
        has_rating = "⭐" in response
        has_phone = "📞" in response
        no_tool_used = not has_maps_url and not has_rating and not has_phone

        print()
        print(f"   📊 التحليل:")
        print(f"      - رابط خريطة: {'✅' if has_maps_url else '❌'}")
        print(f"      - تقييم: {'✅' if has_rating else '❌'}")
        print(f"      - هاتف: {'✅' if has_phone else '❌'}")
        if no_tool_used:
            print(f"      ⚠️  الوكيل رد بدون أداة (سواء سأل توضيح أو اخترع)")

    except Exception as e:
        print(f"❌ خطأ: {e}")
        import traceback
        traceback.print_exc()

print(f"\n{'='*70}")
print("انتهى الاختبار")
print("=" * 70)
