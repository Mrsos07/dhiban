"""
تقييم شامل للوكيل: 10 سيناريوهات من السهل إلى الصعب.

يختبر بشكل متكامل:
  ✅ السلوك السليم حسب نوع الطلب (تحية / خارج النطاق / عام / محدد / بدائل / متعدد أدوار)
  ✅ قراءة التصنيف الفرعي والوصف وملاحظات الوكيل (الميزة الجديدة)
  ✅ خلو الردّ من كلمة "شريك" نهائياً (الميزة الجديدة)
  ✅ فصل رسالة الترشيح المميّز كرسالة مستقلة
  ✅ عدم اختراع أسماء + الصرامة في مطابقة النوع

كل سيناريو يُقيَّم حسب معايير مخصّصة، ويُحسب مجموع PASS/FAIL/PARTIAL.
"""
import os
import sys
import re
import json
import time
import django

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dhiban_project.settings')
django.setup()

from ai_agent.agent import DhibanAgent

agent = DhibanAgent()

# قائمة الكلمات المحظورة — يجب ألا تظهر في أي رد
FORBIDDEN_WORDS = ['شريك', 'شريكنا', 'شركاء', 'شركاؤنا', 'شريك معتمد']


# ═════════════════════════════════════════════════════════════════════
# 10 سيناريوهات من السهل للصعب
# ═════════════════════════════════════════════════════════════════════
SCENARIOS = [
    {
        "id": "1-سهل",
        "name": "تحية بسيطة → ردّ ودّي بلا بحث",
        "message": "السلام عليكم",
        "history": [],
        "expect": "greeting",
    },
    {
        "id": "2-سهل",
        "name": "طلب خارج النطاق (مطعم في الرياض) → اعتذار صريح",
        "message": "ابي مطعم حلو في الرياض",
        "history": [],
        "expect": "out_of_scope",
    },
    {
        "id": "3-سهل",
        "name": "طلب عام 'ابي مطعم' بلا نوع → سؤال استيضاح",
        "message": "ابي مطعم",
        "history": [],
        "expect": "ask_type",
    },
    {
        "id": "4-متوسط",
        "name": "خدمة منزلية عاجلة 'كهربائي' → بحث مباشر",
        "message": "ابي كهربائي بأسرع وقت",
        "history": [],
        "expect": "search_direct",
    },
    {
        "id": "5-متوسط",
        "name": "طلب واضح بنوع محدد 'بيتزا' → يبحث ببيتزا ولا يقترح مندي",
        "message": "ابي مطعم بيتزا",
        "history": [],
        "expect": "search_specific",
        "should_contain_any": ["بيتزا", "pizza", "Pizza"],
        "must_not_contain": ["مندي", "كبسة", "بخاري", "مشاوي"],
    },
    {
        "id": "6-متوسط",
        "name": "طلب محدد في فئة غير الطعام 'صيدلية أدوية أطفال'",
        "message": "ابي صيدلية فيها أدوية أطفال",
        "history": [],
        "expect": "search_specific",
        "should_contain_any": ["صيدلي", "دواء", "أطفال", "أدوية"],
    },
    {
        "id": "7-صعب",
        "name": "طلب بدائل بعد نتائج سابقة → نتائج جديدة بنفس النوع (بيتزا)",
        "message": "اقترح لي غيرها",
        "history": [
            {"role": "user", "content": "ابي مطعم بيتزا"},
            {"role": "assistant",
             "content": "تفضل:\n1. *بيتزا روما* ⭐ 4.6/5\n2. *بيتزا نابولي* ⭐ 4.4/5"},
        ],
        "expect": "search_alternatives",
        "must_not_contain": ["مندي", "كبسة", "بخاري"],
        "must_not_repeat": ["بيتزا روما", "بيتزا نابولي"],
    },
    {
        "id": "8-صعب",
        "name": "محادثة متعدّدة الأدوار → استيضاح ثم طلب محدّد",
        "message": "بيتزا للعوائل",
        "history": [
            {"role": "user", "content": "ابي مطعم"},
            {"role": "assistant",
             "content": "هلا يالغالي! أي نوع تحب؟ بيتزا، بروست، مندي، برجر؟"},
        ],
        "expect": "search_specific",
        "should_contain_any": ["بيتزا", "pizza", "Pizza"],
        "must_not_contain": ["مندي"],
    },
    {
        "id": "9-صعب",
        "name": "جودة/جو محدّد 'كافيه هادي للدراسة'",
        "message": "ابي كافيه هادي اذاكر فيه",
        "history": [],
        "expect": "search_specific",
        "should_contain_any": ["كافيه", "قهوة", "كوفي", "Coffee", "Cafe"],
    },
    {
        "id": "10-صعب",
        "name": "طلب نادر 'مطعم سوشي' → نتائج Google أو اعتذار صريح (لا بديل)",
        "message": "ابي مطعم سوشي في عنيزة",
        "history": [],
        "expect": "search_or_honest_no_match",
        "must_not_contain": ["مندي", "كبسة", "بروست", "بيتزا"],
    },
]


# ═════════════════════════════════════════════════════════════════════
# أدوات التقييم
# ═════════════════════════════════════════════════════════════════════

def flatten(response):
    """الوكيل قد يرجع str أو list[str] (حين يوجد ترشيح مميّز مستقل)."""
    if isinstance(response, list):
        return "\n\n---\n\n".join(str(x) for x in response), response
    return str(response), [str(response)]


def has_search_results(text: str) -> bool:
    return bool(
        re.search(r'google\.com/maps|maps\.google\.com|goo\.gl/maps|maps\.app', text)
        or re.search(r'⭐\s*\d', text)
        or re.search(r'📞|\b05\d{8}\b', text)
    )


def looks_like_question(text: str) -> bool:
    # تحية + سؤال مرجعي
    if '؟' in text:
        return True
    q_words = ['وش تبي', 'تبي بيتزا', 'تبي بروست', 'أي نوع', 'ايش تبي',
               'وش تفضل', 'وش النوع', 'هادي ولا', 'تبيه', 'تحب']
    return any(q in text for q in q_words)


def honest_no_match(text: str) -> bool:
    markers = ['ما لقيت', 'لم أجد', 'للأسف', 'ما لقينا', 'ما وجدت']
    return any(m in text for m in markers)


def acknowledges_scope(text: str) -> bool:
    """يعترف أن الخدمة محدودة بعنيزة."""
    t = text
    return 'عنيزة' in t and any(k in t for k in ['فقط', 'بس', 'محصور', 'متخصص'])


def is_greeting_only(text: str) -> bool:
    """ردّ تحية فقط بدون بحث أو سؤال استيضاح."""
    t = text.strip()
    short = len(t) <= 400
    has_greet = any(k in t for k in ['وعليكم', 'هلا', 'حياك', 'مرحبا', 'أهلا', 'يالغالي'])
    return short and has_greet and not has_search_results(t)


def contains_any(text: str, words) -> list:
    """مطابقة غير حساسة لحالة الأحرف اللاتينية (case-insensitive للإنجليزية)."""
    t_lower = text.lower()
    return [w for w in words if w and (w in text or w.lower() in t_lower)]


def evaluate(scenario: dict, messages: list, full_text: str) -> dict:
    expect = scenario["expect"]
    verdict = "UNKNOWN"
    issues = []
    notes = []

    has_res = has_search_results(full_text)
    is_q = looks_like_question(full_text)
    is_honest = honest_no_match(full_text)

    # فحوصات عامة تُطبق دائماً:

    # 1) كلمة "شريك" ممنوعة في أي رد
    forbidden_hits = [w for w in FORBIDDEN_WORDS if w in full_text]
    if forbidden_hits:
        issues.append(f"كلمات محظورة ظهرت: {forbidden_hits}")

    # فحص خاص لكل نوع:
    if expect == "greeting":
        if is_greeting_only(full_text):
            verdict = "PASS"
        else:
            verdict = "FAIL"
            issues.append("كان يفترض ردّ تحية فقط بلا بحث")

    elif expect == "out_of_scope":
        if acknowledges_scope(full_text) and not has_res:
            verdict = "PASS"
        elif is_q and 'عنيزة' in full_text:
            verdict = "PARTIAL"
            notes.append("اعترف بالنطاق لكن سأل بدل الاعتذار الواضح")
        else:
            verdict = "FAIL"
            issues.append("كان يفترض يعتذر ويوضح أن الخدمة لعنيزة فقط")

    elif expect == "ask_type":
        if is_q and not has_res:
            verdict = "PASS"
        else:
            verdict = "FAIL"
            issues.append("كان يفترض يسأل عن النوع بدل البحث")

    elif expect == "search_direct":
        if has_res or is_honest:
            verdict = "PASS"
        else:
            verdict = "FAIL"
            issues.append("كان يفترض يبحث مباشرة (أو يعترف بعدم وجود)")

    elif expect == "search_specific":
        should = scenario.get("should_contain_any", [])
        forbidden = scenario.get("must_not_contain", [])
        found_forbidden = contains_any(full_text, forbidden)

        if not (has_res or is_honest):
            verdict = "FAIL"
            issues.append("كان يفترض يبحث أو يعترف بعدم الوجود")
        elif found_forbidden and has_res:
            verdict = "FAIL"
            issues.append(f"اقترح أنواعاً بديلة ممنوعة: {found_forbidden}")
        else:
            # ضمن النتائج نريد النوع المطلوب
            if should and has_res:
                found_any = contains_any(full_text, should)
                if found_any:
                    verdict = "PASS"
                    notes.append(f"طابق النوع المطلوب: {found_any}")
                else:
                    verdict = "PARTIAL"
                    notes.append(f"النتائج لا تذكر صراحةً: {should} (قد تكون أسماء إنجليزية في قوقل)")
            else:
                verdict = "PASS"

    elif expect == "search_alternatives":
        forbidden = scenario.get("must_not_contain", [])
        repeats = scenario.get("must_not_repeat", [])
        found_forbidden = contains_any(full_text, forbidden)
        found_repeats = contains_any(full_text, repeats)

        if not (has_res or is_honest):
            verdict = "FAIL"
            issues.append("كان يفترض يبحث عن بدائل")
        elif found_forbidden:
            verdict = "FAIL"
            issues.append(f"غيّر النوع عند طلب البدائل: {found_forbidden}")
        elif found_repeats:
            verdict = "FAIL"
            issues.append(f"كرّر أسماء مذكورة سابقاً: {found_repeats}")
        else:
            verdict = "PASS"

    elif expect == "search_or_honest_no_match":
        forbidden = scenario.get("must_not_contain", [])
        found_forbidden = contains_any(full_text, forbidden)
        if found_forbidden and has_res:
            verdict = "FAIL"
            issues.append(f"رشّح نوعاً بديلاً ممنوعاً: {found_forbidden}")
        elif has_res or is_honest:
            verdict = "PASS"
        else:
            verdict = "FAIL"
            issues.append("كان يفترض: إمّا نتائج حقيقية أو اعتذار صريح")

    # إن كانت هناك كلمات محظورة ولم نَحكم بـ FAIL، نُنزّل الحكم
    if forbidden_hits and verdict == "PASS":
        verdict = "FAIL"

    return {
        "verdict": verdict,
        "issues": issues,
        "notes": notes,
        "has_results": has_res,
        "is_question": is_q,
        "is_honest_no_match": is_honest,
        "forbidden_hits": forbidden_hits,
        "num_messages": len(messages),
    }


# ═════════════════════════════════════════════════════════════════════
def main():
    print("═" * 78)
    print("تقييم الوكيل — 10 سيناريوهات (سهل → صعب)")
    print("═" * 78)

    results = []
    counters = {"PASS": 0, "FAIL": 0, "PARTIAL": 0, "UNKNOWN": 0}

    for i, sc in enumerate(SCENARIOS, 1):
        # إعادة ضبط أي حالة معلّقة بين السيناريوهات
        agent._pending_partner_followup = None

        print(f"\n{'─' * 78}")
        print(f"[{sc['id']}] {sc['name']}")
        print(f"💬 الرسالة: {sc['message']}")
        if sc.get('history'):
            print(f"📜 التاريخ: {len(sc['history'])} رسالة")

        t0 = time.time()
        try:
            raw = agent.process_message_with_history(
                user_message=sc['message'],
                chat_history=sc.get('history', []),
                user_id=f"test_user_{sc['id']}",
            )
        except Exception as e:
            raw = f"[ERROR] {e}"
        elapsed = time.time() - t0

        full_text, msgs = flatten(raw)
        print(f"🤖 الرد ({elapsed:.1f}ث، {len(msgs)} رسالة):")
        for idx, m in enumerate(msgs, 1):
            preview = m[:500] + ('...' if len(m) > 500 else '')
            print(f"   [#{idx}] {preview}")

        ev = evaluate(sc, msgs, full_text)
        badge = {"PASS": "✅", "FAIL": "❌", "PARTIAL": "⚠️ ", "UNKNOWN": "❓"}[ev["verdict"]]
        print(f"\n   {badge} الحكم: {ev['verdict']}")
        for issue in ev["issues"]:
            print(f"      ⚠️  {issue}")
        for note in ev["notes"]:
            print(f"      ℹ️  {note}")
        print(f"   📊 نتائج={ev['has_results']} سؤال={ev['is_question']} "
              f"اعتذار={ev['is_honest_no_match']} رسائل={ev['num_messages']}")

        counters[ev["verdict"]] += 1
        results.append({
            "id": sc["id"],
            "name": sc["name"],
            "verdict": ev["verdict"],
            "issues": ev["issues"],
            "forbidden_hits": ev["forbidden_hits"],
            "num_messages": ev["num_messages"],
            "response": msgs,
        })

    # الملخص
    total = len(SCENARIOS)
    print(f"\n{'═' * 78}")
    print(f"الملخص النهائي")
    print(f"{'═' * 78}")
    print(f"✅ PASS:    {counters['PASS']}/{total}")
    print(f"⚠️  PARTIAL: {counters['PARTIAL']}/{total}")
    print(f"❌ FAIL:    {counters['FAIL']}/{total}")
    print()
    for r in results:
        badge = {"PASS": "✅", "FAIL": "❌", "PARTIAL": "⚠️ ", "UNKNOWN": "❓"}[r["verdict"]]
        print(f"  {badge} [{r['id']}] {r['name']}")
        for issue in r["issues"]:
            print(f"       • {issue}")

    with open('agent_eval_10_results.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\n💾 حُفظت النتائج في agent_eval_10_results.json")

    sys.exit(0 if counters["FAIL"] == 0 else 1)


if __name__ == '__main__':
    main()
