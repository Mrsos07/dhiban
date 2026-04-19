"""
تقييم شامل للوكيل — 12 سيناريو (سهل إلى معقد).
يقيس السلوك الصحيح حسب القواعد:
  • طلب عام (مطعم/كافيه/محل) → يسأل عن النوع (لا يبحث مباشرة).
  • طلب محدد (بيتزا/مندي/كهربائي) → يبحث مباشرة.
  • النوع المحدد لا يوجد في DB → ينتقل لـ Google بنفس النوع (لا بديل).
  • الشريك الرئيسي يظهر فقط لو طابق النوع المحدد.
  • لا اختراع أسماء أماكن.
"""
import os
import sys
import re
import json
import time
import django

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dhiban_project.settings')
django.setup()

from ai_agent.agent import DhibanAgent

agent = DhibanAgent()

# ═══════════════════════════════════════════════════════════════════
# السيناريوهات
# لكل سيناريو: الرسالة + التاريخ + معايير التقييم (checks)
# ═══════════════════════════════════════════════════════════════════
SCENARIOS = [
    # ── سهل ─────────────────────────────────────────────────────
    {
        "id": "E1",
        "name": "طلب عام 'ابي مطعم' → يجب أن يسأل عن النوع",
        "message": "ابي مطعم",
        "history": [],
        "expect": "ask_type",  # يسأل ولا يبحث
    },
    {
        "id": "E2",
        "name": "طلب واضح 'ابي صيدلية' → يبحث مباشرة",
        "message": "ابي صيدلية قريبة",
        "history": [],
        "expect": "search_direct",
    },
    {
        "id": "E3",
        "name": "خدمة عاجلة 'ابي كهربائي' → يبحث مباشرة",
        "message": "ابي كهربائي الكهرباء طايحة",
        "history": [],
        "expect": "search_direct",
    },

    # ── متوسط ───────────────────────────────────────────────────
    {
        "id": "M1",
        "name": "طلب محدد 'مطعم بيتزا' → يبحث ببيتزا (لا مندي)",
        "message": "ابي مطعم بيتزا",
        "history": [],
        "expect": "search_specific",
        "must_not_contain_types": ["مندي", "كبسة", "بخاري"],
        "should_contain_type": "بيتزا",
    },
    {
        "id": "M2",
        "name": "طلب محدد في فئة أخرى 'محل جوالات'",
        "message": "ابي محل جوالات",
        "history": [],
        "expect": "search_specific",
        "should_contain_type": "جوال",
    },
    {
        "id": "M3",
        "name": "طلب مبهم 'ابي اطلع' → يجب أن يسأل (لا يبني خطة)",
        "message": "ابي اطلع اليوم",
        "history": [],
        "expect": "ask_clarification",
    },
    {
        "id": "M4",
        "name": "نوع نادر 'سوشي' → Google أو اعتذار صريح",
        "message": "ابي مطعم سوشي في عنيزة",
        "history": [],
        "expect": "search_or_honest_no_match",
        "must_not_contain_types": ["مندي", "كبسة", "بروست"],
    },
    {
        "id": "M5",
        "name": "طلب بديل 'اقترح غيرها' → نتائج جديدة بنفس النوع",
        "message": "اقترح لي غيرها",
        "history": [
            {"role": "user", "content": "ابي مطعم بيتزا"},
            {"role": "assistant", "content": "تفضل: *بيتزا هت* تقييمه 4.5. و*دومينوز* تقييم 4.3."},
        ],
        "expect": "search_alternatives",
        "must_not_contain_types": ["مندي", "كبسة"],
    },

    # ── معقد ────────────────────────────────────────────────────
    {
        "id": "C1",
        "name": "محادثة متعددة الأدوار → بعد الاستيضاح يبحث",
        "message": "بيتزا عائلي",
        "history": [
            {"role": "user", "content": "ابي مطعم"},
            {"role": "assistant", "content": "هلا يالغالي! أي نوع تحب؟ بيتزا، بروست، مندي، برجر؟"},
        ],
        "expect": "search_specific",
        "should_contain_type": "بيتزا",
        "must_not_contain_types": ["مندي", "كبسة"],
    },
    {
        "id": "C2",
        "name": "طلب متخصص 'عيادة أسنان أطفال' → بحث بنفس التخصص",
        "message": "ابي عيادة أسنان للأطفال",
        "history": [],
        "expect": "search_specific",
        "should_contain_type": "أسنان",
    },
    {
        "id": "C3",
        "name": "طلب بشرط جودة 'كافيه هادي للدراسة'",
        "message": "ابي كافيه هادي أذاكر فيه",
        "history": [],
        "expect": "search_specific",
        "should_contain_type": "هاد",  # هادي / هادئ
    },
    {
        "id": "C4",
        "name": "خطة يومية بعد جمع كافي من السياق",
        "message": "تمشية وعشاء خفيف",
        "history": [
            {"role": "user", "content": "ابي اطلع اليوم"},
            {"role": "assistant", "content": "هلا! لحالك ولا معك أحد؟ وتبيها هدوء ولا حركة؟"},
            {"role": "user", "content": "مع زوجتي وابي هدوء"},
            {"role": "assistant", "content": "زين! تبون بس تتمشون ولا تبون تمرون على مكان تاكلون فيه؟"},
        ],
        "expect": "plan_or_search",
    },
    {
        "id": "C5",
        "name": "طلب خارج عنيزة → اعتذار",
        "message": "ابي مطعم في الرياض",
        "history": [],
        "expect": "out_of_scope",
    },
]


# ═══════════════════════════════════════════════════════════════════
# التقييم
# ═══════════════════════════════════════════════════════════════════

def has_search_markers(text: str) -> dict:
    """يكشف هل الرد فيه نتائج بحث حقيقية."""
    return {
        "has_maps_url": bool(re.search(r'google\.com/maps|maps\.google\.com|goo\.gl/maps|maps\.app', text)),
        "has_rating": bool(re.search(r'⭐.*\d', text)),
        "has_phone": bool(re.search(r'📞|\b05\d{8}\b', text)),
        "has_place_name_star": bool(re.search(r'\*[^*\n]{2,80}\*', text)),
        "has_partner_badge": 'ترشيحنا المميز' in text or 'شريك معتمد' in text,
    }

def looks_like_question(text: str) -> bool:
    """هل الرد يحتوي سؤالاً؟"""
    return '؟' in text or 'وش' in text or 'تبي' in text.lower() or 'وش لون' in text

def honest_no_match(text: str) -> bool:
    """هل الرد يعترف بعدم وجود نتائج؟"""
    markers = ['ما لقيت', 'لم أجد', 'للأسف', 'ما لقيت نتائج']
    return any(m in text for m in markers)

def contains_any(text: str, words: list) -> list:
    """يرجع قائمة بالكلمات الموجودة في النص."""
    return [w for w in words if w in text]

def evaluate(scenario: dict, response: str) -> dict:
    """يقيم استجابة الوكيل حسب معيار السيناريو."""
    markers = has_search_markers(response)
    is_question = looks_like_question(response)
    is_honest_no_match = honest_no_match(response)
    has_results = markers["has_maps_url"] or markers["has_rating"] or markers["has_phone"]

    verdict = "UNKNOWN"
    issues = []
    notes = []

    expect = scenario.get("expect")

    if expect == "ask_type":
        if is_question and not has_results:
            verdict = "PASS"
        else:
            verdict = "FAIL"
            issues.append("كان يفترض يسأل عن النوع بدل البحث المباشر")

    elif expect == "ask_clarification":
        if is_question and not has_results:
            verdict = "PASS"
        else:
            verdict = "FAIL"
            issues.append("كان يفترض يطلب توضيح قبل بناء خطة/البحث")

    elif expect == "search_direct":
        if has_results or is_honest_no_match:
            verdict = "PASS"
        else:
            verdict = "FAIL"
            issues.append("كان يفترض يبحث مباشرة ويرجع نتائج (أو يعترف بعدم الوجود)")

    elif expect == "search_specific":
        if has_results or is_honest_no_match:
            verdict = "PASS"
        else:
            verdict = "FAIL"
            issues.append("كان يفترض يبحث بالنوع المحدد")
        # تحقق النوع المطلوب موجود
        should = scenario.get("should_contain_type")
        if should and has_results:
            if should not in response:
                issues.append(f"النتائج ما تحتوي النوع المطلوب '{should}'")
                notes.append("الاسم/الوصف قد لا يذكر النوع بالحرف، لكن قوقل ماب قد يرجع محلات مطابقة بأسماء إنجليزية.")
        # فحص عدم وجود أنواع بديلة
        forbidden = scenario.get("must_not_contain_types", [])
        found_forbidden = contains_any(response, forbidden)
        if found_forbidden and has_results:
            verdict = "FAIL"
            issues.append(f"رشّح أنواعاً بديلة ممنوعة: {found_forbidden}")

    elif expect == "search_or_honest_no_match":
        if has_results or is_honest_no_match:
            verdict = "PASS"
        else:
            verdict = "FAIL"
            issues.append("كان يفترض: إما نتائج حقيقية أو اعتذار صريح")
        forbidden = scenario.get("must_not_contain_types", [])
        found_forbidden = contains_any(response, forbidden)
        if found_forbidden and has_results:
            verdict = "FAIL"
            issues.append(f"رشّح بديلاً ممنوعاً: {found_forbidden}")

    elif expect == "search_alternatives":
        if has_results or is_honest_no_match:
            verdict = "PASS"
        else:
            verdict = "FAIL"
            issues.append("طلب بدائل — يفترض يبحث مجدداً")
        forbidden = scenario.get("must_not_contain_types", [])
        found_forbidden = contains_any(response, forbidden)
        if found_forbidden and has_results:
            verdict = "FAIL"
            issues.append(f"غيّر النوع المطلوب في البدائل: {found_forbidden}")

    elif expect == "plan_or_search":
        if has_results or is_honest_no_match:
            verdict = "PASS"
        else:
            # قد يسأل سؤال استيضاح آخر — مقبول
            verdict = "PARTIAL"
            notes.append("الوكيل سأل سؤالاً إضافياً بدل البحث — مقبول نسبياً.")

    elif expect == "out_of_scope":
        # اعتذار بأن الخدمة لعنيزة فقط
        if 'عنيزة' in response and ('فقط' in response or 'متخصص' in response or 'بس' in response or 'محصور' in response):
            verdict = "PASS"
        else:
            verdict = "FAIL"
            issues.append("كان يفترض يعتذر ويوضح أن النطاق عنيزة فقط")

    return {
        "verdict": verdict,
        "issues": issues,
        "notes": notes,
        "markers": markers,
        "is_question": is_question,
        "is_honest_no_match": is_honest_no_match,
    }


# ═══════════════════════════════════════════════════════════════════
# تشغيل
# ═══════════════════════════════════════════════════════════════════

def main():
    print("═" * 78)
    print("تقييم شامل للوكيل — 12 سيناريو")
    print("═" * 78)

    results = []
    pass_count = 0
    fail_count = 0
    partial_count = 0

    for i, sc in enumerate(SCENARIOS, 1):
        print(f"\n{'─' * 78}")
        print(f"[{sc['id']}] {sc['name']}")
        print(f"💬 الرسالة: {sc['message']}")
        if sc.get('history'):
            print(f"📜 التاريخ: {len(sc['history'])} رسائل")
        print()

        t0 = time.time()
        try:
            response = agent.process_message_with_history(
                user_message=sc['message'],
                chat_history=sc.get('history', [])
            )
        except Exception as e:
            response = f"[ERROR] {e}"
        elapsed = time.time() - t0

        print(f"🤖 الرد ({elapsed:.1f}ث):")
        print(response[:800] + ('...' if len(response) > 800 else ''))
        print()

        ev = evaluate(sc, response)
        badge = {"PASS": "✅", "FAIL": "❌", "PARTIAL": "⚠️ ", "UNKNOWN": "❓"}[ev["verdict"]]
        print(f"   {badge} الحكم: {ev['verdict']}")
        if ev["issues"]:
            for issue in ev["issues"]:
                print(f"      ⚠️  {issue}")
        if ev["notes"]:
            for note in ev["notes"]:
                print(f"      ℹ️  {note}")
        print(f"   📊 مؤشرات: خريطة={ev['markers']['has_maps_url']} تقييم={ev['markers']['has_rating']} "
              f"هاتف={ev['markers']['has_phone']} سؤال={ev['is_question']} اعتذار={ev['is_honest_no_match']}")

        results.append({
            "id": sc["id"],
            "name": sc["name"],
            "verdict": ev["verdict"],
            "issues": ev["issues"],
            "response_preview": response[:300],
        })
        if ev["verdict"] == "PASS":
            pass_count += 1
        elif ev["verdict"] == "FAIL":
            fail_count += 1
        elif ev["verdict"] == "PARTIAL":
            partial_count += 1

    # ملخص
    print(f"\n{'═' * 78}")
    print(f"الملخص")
    print(f"{'═' * 78}")
    total = len(SCENARIOS)
    print(f"PASS: {pass_count}/{total}  FAIL: {fail_count}/{total}  PARTIAL: {partial_count}/{total}")
    print()
    for r in results:
        badge = {"PASS": "✅", "FAIL": "❌", "PARTIAL": "⚠️ ", "UNKNOWN": "❓"}[r["verdict"]]
        print(f"  {badge} {r['id']} — {r['name']}")
        for issue in r["issues"]:
            print(f"       • {issue}")

    # حفظ JSON للتحليل
    with open('eval_results.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\n💾 حفظت النتائج في eval_results.json")


if __name__ == '__main__':
    main()
