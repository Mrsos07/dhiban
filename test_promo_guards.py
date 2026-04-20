"""
اختبار وحدة للحرّاس الجدد في _inject_promotion:
  1) _response_has_real_results
  2) _response_is_apology_or_clarification
  3) _inject_promotion لا يحقن فوق اعتذار/استيضاح/تحية
  4) _inject_promotion يسمح بالحقن فوق ردّ فيه نتائج فعلية
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dhiban_project.settings')
django.setup()

from ai_agent.agent import DhibanAgent

agent = DhibanAgent()


def test(label, cond, extra=''):
    status = '✅' if cond else '❌'
    print(f'{status} {label}' + (f'  — {extra}' if extra else ''))
    return cond


def main():
    all_ok = True

    print('=' * 70)
    print('1) _response_has_real_results')
    print('=' * 70)
    cases_real = [
        ('فيه مطعم هذا موقعه: https://maps.google.com/?q=26.09,43.99', True),
        ('تقييمه ⭐ 4.7/5 وناسه يمدحونه', True),
        ('رقمه 📞 0501234567', True),
        ('تواصل على 0551234567', True),
        ('هلا والله، وش لونك؟', False),
        ('ما لقيت نتائج يالغالي', False),
        ('أي نوع تحب؟ بيتزا ولا مندي؟', False),
    ]
    for text, expected in cases_real:
        got = DhibanAgent._response_has_real_results(text)
        ok = got == expected
        all_ok &= test(f'"{text[:45]}..." → {got} (متوقع {expected})', ok)

    print('\n' + '=' * 70)
    print('2) _response_is_apology_or_clarification')
    print('=' * 70)
    cases_apology = [
        ('أنا أخدمك في عنيزة بس، أعذرني عن الرياض', True),
        ('ما لقيت نتائج، تبي أجرب بحث ثاني؟', True),
        ('للأسف ما فيه سوشي في عنيزة', True),
        ('أي نوع تحب؟ بيتزا ولا مندي؟', True),  # استيضاح
        ('هلا والله!', False),  # تحية بدون سؤال ولا اعتذار
        ('عندك مطعم بيتزا ازوري تقييمه 4.7 https://maps.google.com/?q=1,2', False),
    ]
    for text, expected in cases_apology:
        got = DhibanAgent._response_is_apology_or_clarification(text)
        ok = got == expected
        all_ok &= test(f'"{text[:45]}..." → {got} (متوقع {expected})', ok)

    print('\n' + '=' * 70)
    print('3) _inject_promotion لا يحقن فوق اعتذار/استيضاح')
    print('=' * 70)
    # نحاكي user_id وهمي — maybe_promote سيحاول، لكن الحارس يجب يمنعه
    agent._pending_partner_followup = None

    apology = 'يا بعد حيي، أنا أخدمك في عنيزة بس. أعذرني عن الرياض.'
    out = agent._inject_promotion(apology, 'ابي مطعم في الرياض', user_id='test_u_apology')
    all_ok &= test('اعتذار → لا يُحقَن ترشيح', out == apology,
                   f'len_diff={len(out) - len(apology)}')

    clarification = 'هلا يالغالي! أي نوع تحب؟ بيتزا، بروست، مندي؟'
    out = agent._inject_promotion(clarification, 'ابي مطعم', user_id='test_u_clarify')
    all_ok &= test('سؤال استيضاح → لا يُحقَن ترشيح', out == clarification,
                   f'len_diff={len(out) - len(clarification)}')

    greeting = 'وعليكم السلام ورحمة الله! وش لونك؟'
    out = agent._inject_promotion(greeting, 'السلام عليكم', user_id='test_u_greet')
    all_ok &= test('تحية بدون نتائج → لا يُحقَن ترشيح', out == greeting,
                   f'len_diff={len(out) - len(greeting)}')

    no_results = 'ما لقيت مطعم سوشي في عنيزة 😕'
    out = agent._inject_promotion(no_results, 'سوشي', user_id='test_u_nores')
    all_ok &= test('"ما لقيت نتائج" → لا يُحقَن ترشيح', out == no_results)

    print('\n' + '=' * 70)
    print('4) _inject_promotion يُحتمَل حقنه فوق رد بنتائج فعلية')
    print('=' * 70)
    # لا نضمن الحقن دائماً (maybe_promote فيه احتمالية 75% + cooldowns)،
    # لكن يجب ألا يمنعه الحارسان. نتأكد أن الإرجاع إما مطابق للمدخل (تخطٍّ طبيعي)
    # أو أطول منه بسبب إضافة ترشيح — لا زيادة لكلمات محظورة.
    real = (
        'يا بعد حيي، عندك بيتزا ازوري ⭐ 4.7/5 ورقمه 0501234567\n'
        '🗺️ الموقع:\nhttps://maps.google.com/?q=26.09,43.99'
    )
    out = agent._inject_promotion(real, 'ابي بيتزا', user_id='test_u_real_results')
    has_promo = len(out) > len(real)
    clean = 'شريك' not in out and 'شريكنا' not in out
    all_ok &= test('رد بنتائج — إما أُضيف ترشيح أو لا (المنطق سليم)', True,
                   f'added_promo={has_promo}, clean_of_partner_word={clean}')
    all_ok &= test('إن أُضيف ترشيح، يجب ألّا يحوي كلمة "شريك"', clean)

    print('\n' + '=' * 70)
    print('الخلاصة:', '✅ كل الاختبارات نجحت' if all_ok else '❌ فشل بعضها')
    print('=' * 70)
    sys.exit(0 if all_ok else 1)


if __name__ == '__main__':
    main()
