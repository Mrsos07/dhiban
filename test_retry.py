"""إعادة اختبار السيناريوهين الفاشلين بعد تحديث البرومبت."""
import os, sys, django, json, re, time

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dhiban_project.settings')
django.setup()

from ai_agent.agent import DhibanAgent
agent = DhibanAgent()

CASES = [
    ("M2", "ابي محل جوالات", []),
    ("C3", "ابي كافيه هادي أذاكر فيه", []),
    # نفحص أيضاً أن الأسئلة العامة لا تزال تُفتَح عند الحاجة
    ("E1-recheck", "ابي مطعم", []),
    ("E-cafe", "ابي كافيه", []),
]

def has_results(text):
    return bool(re.search(r'google\.com/maps|maps\.google\.com|goo\.gl/maps|⭐|📞', text))

def is_question(text):
    return '؟' in text

out = []
for cid, msg, hist in CASES:
    print(f"\n── [{cid}] {msg}")
    t0 = time.time()
    resp = agent.process_message_with_history(msg, hist)
    elapsed = time.time() - t0
    hr = has_results(resp)
    iq = is_question(resp)
    print(f"   زمن: {elapsed:.1f}ث | نتائج: {hr} | سؤال: {iq}")
    print(f"   {resp[:400]}")
    out.append({"id": cid, "msg": msg, "has_results": hr, "is_question": iq, "preview": resp[:400]})

with open('retry_results.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print("\nحفظت في retry_results.json")
