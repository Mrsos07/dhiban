"""
سكريبت تشخيص الوكيل - يحاكي ما يحدث في الواتساب بالضبط
شغّله بـ: python manage.py shell < test_agent_debug.py
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dhiban_project.settings')

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ────────────────────────────────────────────────
print("=" * 60)
print("TEST 1: search_suppliers مباشرة")
print("=" * 60)
from ai_agent.tools import search_suppliers, format_search_results, search_google_places, format_google_results

results = search_suppliers(category_name="مطعم", limit=3)
print(f"عدد النتائج من DB: {len(results)}")
for r in results:
    print(f"  اسم: {r.get('name')}")
    print(f"  هاتف: {r.get('phone')}")
    print(f"  maps_url: {r.get('maps_url')}")
    print()

if results:
    formatted = format_search_results({'database_results': results, 'google_results': [], 'total': len(results)})
    print("─── النص المنسَّق (سيُرسل للواتساب) ───")
    print(repr(formatted))
    print("─── النص كما سيظهر ───")
    print(formatted)

# ────────────────────────────────────────────────
print("\n" + "=" * 60)
print("TEST 2: search_suppliers كوفي/قهوة")
print("=" * 60)
results2 = search_suppliers(category_name="كافيه", limit=3)
results2b = search_suppliers(keywords=["قهوة", "كوفي", "كافيه"], limit=3)
print(f"نتائج category='كافيه': {len(results2)}")
print(f"نتائج keywords=['قهوة','كوفي','كافيه']: {len(results2b)}")

# ────────────────────────────────────────────────
print("\n" + "=" * 60)
print("TEST 3: process_message_with_history (نفس ما يستخدمه الواتساب)")
print("=" * 60)
from ai_agent.agent import dhiban_agent

response = dhiban_agent.process_message_with_history("أبي مطعم زين في عنيزة", chat_history=[])
print("─── رد الوكيل ───")
print(repr(response))
print("─── كما سيظهر ───")
print(response)

# ────────────────────────────────────────────────
print("\n" + "=" * 60)
print("TEST 4: Google Places مباشرة")
print("=" * 60)
gresults = search_google_places(query="مطعم عنيزة", limit=3, save_results=False)
print(f"عدد النتائج من Google: {len(gresults)}")
for r in gresults:
    print(f"  اسم: {r.get('name')}")
    print(f"  هاتف: {r.get('phone')}")
    print(f"  maps_url: {r.get('maps_url')}")
    print()

# ────────────────────────────────────────────────
print("\n" + "=" * 60)
print("TEST 5: get_primary_phone على الموردين")
print("=" * 60)
from suppliers.models import Supplier
suppliers = Supplier.objects.filter(is_active=True)[:5]
for s in suppliers:
    print(f"  {s.name_ar}: phone_numbers={s.phone_numbers} | get_primary_phone={s.get_primary_phone()}")
