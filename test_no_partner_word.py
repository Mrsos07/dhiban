"""
اختبار صارم: ضمان أن كلمة "شريك" وصيغها لا تظهر في أي نص يصل للمستخدم.
  1) format_supplier_response لمورد is_partner=True
  2) _format_partner_block (رسالة الترشيح المستقلة)
  3) _format_promotion (صياغات الترويج العشوائية — كلها)
  4) _sanitize_partner_wording يستبدل الكلمة حتى لو أفلتت من الـ prompt
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dhiban_project.settings')
django.setup()

FORBIDDEN = ['شريك', 'شريكنا', 'شركاء', 'شركاؤنا', 'ترويج', 'إعلان', 'مُموَّل']


def contains_forbidden(text: str):
    return [w for w in FORBIDDEN if w in text]


def test_case(label, text: str, allow_partner_in_internal_only=False):
    hits = contains_forbidden(text)
    ok = not hits
    status = '✅' if ok else '❌'
    print(f'{status} {label}')
    if hits:
        print(f'   كلمات محظورة وُجدت: {hits}')
        print(f'   النص:\n{text}\n')
    return ok


def main():
    all_ok = True

    # 1) format_supplier_response
    print('=' * 72)
    print('1) format_supplier_response لمورد is_partner=True')
    print('=' * 72)
    from ai_agent.tools import format_supplier_response
    sample = {
        'name': 'مطعم التجربة',
        'rating': 4.6,
        'reviews_count': 120,
        'subcategory': 'بيتزا',
        'services': ['توصيل', 'جلسات عائلية'],
        'description': 'مطعم بيتزا إيطالية يقدم توصيل سريع.',
        'agent_notes': 'متخصص بالبيتزا الإيطالية، خيار ممتاز للعوائل.',
        'phone': '0500000001',
        'location': {'lat': 26.09, 'lng': 43.99, 'address': 'عنيزة'},
        'is_partner': True,
    }
    rendered = format_supplier_response(sample)
    print(rendered)
    print()
    all_ok &= test_case('خلو من "شريك" في format_supplier_response', rendered)
    all_ok &= test_case('يحتوي على "مورد مرشّح" البديل',
                        'مورد مرشّح' in rendered and 'OK' or rendered,
                        )  # fake for re-use

    # re-check positive case
    status = '✅' if 'مورد مرشّح' in rendered else '❌'
    print(f'{status} يحتوي على بديل "مورد مرشّح"')
    all_ok &= ('مورد مرشّح' in rendered)

    # 2) _format_partner_block
    print('\n' + '=' * 72)
    print('2) _format_partner_block (الرسالة المستقلة)')
    print('=' * 72)
    from ai_agent.agent import DhibanAgent
    agent = DhibanAgent()
    partner = {
        'name': 'مخبز التجربة',
        'rating': 4.8,
        'total_ratings': 300,
        'agent_notes': 'معجنات طازة يومياً.',
        'address': 'عنيزة - شارع الملك عبدالله',
        'phone': '0500000099',
        'maps_url': 'https://maps.google.com/?q=26.1,44.0',
    }
    block = agent._format_partner_block(partner)
    print(block)
    print()
    all_ok &= test_case('خلو من "شريك" في _format_partner_block', block)
    status = '✅' if 'مورد مرشّح' in block else '❌'
    print(f'{status} يحتوي على بديل "مورد مرشّح"')
    all_ok &= ('مورد مرشّح' in block)

    # 3) _format_promotion — كل القوالب
    print('\n' + '=' * 72)
    print('3) _format_promotion — فحص 20 صياغة عشوائية')
    print('=' * 72)
    from ai_agent.promotions import _format_promotion
    promo_partner = {
        'name': 'التجربة',
        'category': 'مطعم',
        'rating': 4.7,
        'notes': 'خيار عائلي رائع.',
        'phone': '0500000001',
        'address': 'عنيزة',
        'maps_url': 'https://maps.google.com/?q=26.09,43.99',
    }
    promo_ok = True
    seen_templates = set()
    for i in range(20):
        promo = _format_promotion(promo_partner)
        # أخذ أول سطر فقط للتوقيع
        sig = promo.split('\n')[0][:50]
        seen_templates.add(sig)
        hits = contains_forbidden(promo)
        if hits:
            print(f'   ❌ عيّنة {i}: كلمات محظورة {hits}')
            print(f'   {promo}\n')
            promo_ok = False
    status = '✅' if promo_ok else '❌'
    print(f'{status} كل القوالب العشوائية خالية من كلمات محظورة '
          f'({len(seen_templates)} قالب مختلف شُوهد)')
    all_ok &= promo_ok

    # 4) _sanitize_partner_wording — الحارس اللغوي النهائي
    print('\n' + '=' * 72)
    print('4) _sanitize_partner_wording — الحارس اللغوي النهائي')
    print('=' * 72)
    cases = [
        ('شريكنا المعتمد *كافيه س* ينصح فيه.',
         'يجب أن تُستبدل "شريكنا المعتمد" بـ "مرشّحنا"'),
        ('شريك معتمد عندنا.',
         'يجب أن تُستبدل "شريك معتمد"'),
        ('الشريك المعتمد قيمته عالية.',
         'يجب أن تُستبدل "الشريك المعتمد"'),
        ('هذا شريك قوي.',
         'يجب أن تُستبدل "شريك" المفردة'),
        ('قائمة شركاء معتمدين.',
         'يجب أن تُستبدل "شركاء معتمدين"'),
        ('مجرد ترويج إعلان مموّل.',
         'يجب أن تُستبدل "ترويج/إعلان/مموّل"'),
        ('شريكنا الأفضل.',
         'يجب أن تُستبدل "شريكنا"'),
    ]
    for before, hint in cases:
        after = DhibanAgent._sanitize_partner_wording(before)
        hits = contains_forbidden(after)
        ok = not hits
        status = '✅' if ok else '❌'
        print(f'{status} {hint}')
        print(f'   قبل:  {before}')
        print(f'   بعد:  {after}')
        if hits:
            print(f'   كلمات محظورة بقيت: {hits}')
        all_ok &= ok

    # 5) حالة طبيعية: نص لا يحوي شيئاً محظوراً لا يتغير
    print('\n' + '=' * 72)
    print('5) نص بلا كلمات محظورة يبقى كما هو')
    print('=' * 72)
    plain = 'مطعم بيتزا التجربة ⭐ 4.7/5 - رابط: https://maps.google.com'
    sanitized = DhibanAgent._sanitize_partner_wording(plain)
    ok = (plain == sanitized)
    status = '✅' if ok else '❌'
    print(f'{status} النص الطبيعي غير متغيّر')
    if not ok:
        print(f'   قبل: {plain}')
        print(f'   بعد: {sanitized}')
    all_ok &= ok

    # 6) _finalize_response يطبّق الحارس على كل رسائل الرد (رئيسية + ثانوية)
    print('\n' + '=' * 72)
    print('6) _finalize_response يطبّق الحارس على جميع الرسائل')
    print('=' * 72)
    agent._pending_partner_followup = 'رسالة ثانية فيها شريك معتمد.'
    result = agent._finalize_response('رد رئيسي يذكر شريكنا.')
    assert isinstance(result, list) and len(result) == 2, 'expected list of 2'
    main_msg, follow_msg = result
    ok_main = not contains_forbidden(main_msg)
    ok_follow = not contains_forbidden(follow_msg)
    all_ok &= ok_main and ok_follow
    print(f'{"✅" if ok_main else "❌"} الرسالة الرئيسية نظيفة: {main_msg}')
    print(f'{"✅" if ok_follow else "❌"} رسالة الترشيح نظيفة: {follow_msg}')

    print('\n' + '=' * 72)
    print('الخلاصة:', '✅ كل الاختبارات نجحت' if all_ok else '❌ فشل بعضها')
    print('=' * 72)
    sys.exit(0 if all_ok else 1)


if __name__ == '__main__':
    main()
