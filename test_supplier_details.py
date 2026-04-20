"""
اختبار دقيق لقراءة تفاصيل المورد (التصنيف الفرعي + الوصف + ملاحظات الوكيل + الخدمات)
في نتائج search_suppliers وفي format_supplier_response.

يغطي:
  1) search_suppliers يرجّع dict مع كل الحقول الجديدة.
  2) الحقول غير فارغة (description كامل غير مقطوع).
  3) format_supplier_response يُظهر التصنيف الفرعي والوصف وملاحظات الوكيل والخدمات.
  4) البحث بكلمة تظهر فقط في description أو agent_notes يجد المورد.
  5) البحث بكلمة subcategory يجد المورد المناسب دون الخلط.
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dhiban_project.settings')
django.setup()

from suppliers.models import Category, SubCategory, Supplier
from ai_agent.tools import search_suppliers, format_supplier_response


def setup_fixtures():
    """ينشئ بيانات تجريبية غير مدمّرة (تبقى معلّمة كـ TEST-)."""
    cat, _ = Category.objects.get_or_create(
        name_ar='TEST-مطعم',
        defaults={'name_en': 'TEST-Restaurant', 'icon': 'shop'},
    )
    sub_pizza, _ = SubCategory.objects.get_or_create(
        category=cat, name_ar='بيتزا',
        defaults={'name_en': 'Pizza'},
    )
    sub_mandi, _ = SubCategory.objects.get_or_create(
        category=cat, name_ar='مندي',
        defaults={'name_en': 'Mandi'},
    )

    pizza_supplier, _ = Supplier.objects.update_or_create(
        name_ar='TEST-بيتزا ديلوكس',
        defaults={
            'name_en': 'Pizza Deluxe',
            'category': cat,
            'subcategory': sub_pizza,
            'description': 'مطعم بيتزا إيطالية أصلية بعجينة رقيقة، يقدم توصيل سريع داخل عنيزة وجلسات عائلية مريحة.',
            'agent_notes': 'متخصص بالبيتزا الإيطالية الفاخرة، خيار ممتاز للعوائل، أسعاره متوسطة، عنده توصيل.',
            'services': ['توصيل', 'جلسات عائلية', 'طلبات خاصة', 'بيتزا نباتية'],
            'rating': 4.7,
            'reviews_count': 210,
            'phone_numbers': ['0500000001'],
            'location': {'lat': 26.09, 'lng': 43.99, 'address': 'عنيزة - شارع الملك عبدالله'},
            'is_active': True,
            'is_partner': False,
        },
    )

    mandi_supplier, _ = Supplier.objects.update_or_create(
        name_ar='TEST-مندي الأصيل',
        defaults={
            'name_en': 'Original Mandi',
            'category': cat,
            'subcategory': sub_mandi,
            'description': 'بيت المندي والمظبي على الطريقة النجدية الأصيلة.',
            'agent_notes': 'متخصص بالمندي واللحوم المشوية، أكل تقليدي نجدي.',
            'services': ['مندي', 'مظبي', 'ذبائح'],
            'rating': 4.5,
            'reviews_count': 130,
            'phone_numbers': ['0500000002'],
            'location': {'lat': 26.10, 'lng': 44.00, 'address': 'عنيزة - الحي الجنوبي'},
            'is_active': True,
            'is_partner': False,
        },
    )
    return cat, pizza_supplier, mandi_supplier


def teardown_fixtures(cat, *suppliers):
    for s in suppliers:
        s.delete()
    SubCategory.objects.filter(category=cat).delete()
    cat.delete()


def test_case(label, condition, detail=''):
    status = '✅' if condition else '❌'
    print(f'{status} {label}' + (f'  — {detail}' if detail else ''))
    return condition


def main():
    cat, pizza, mandi = setup_fixtures()
    all_ok = True
    try:
        print('=' * 72)
        print('1) البحث عن "بيتزا" في مطعم — يجب أن يرجع pizza ويتجاهل mandi')
        print('=' * 72)
        results = search_suppliers(
            category_name='TEST-مطعم',
            keywords=['بيتزا'],
            limit=5,
            randomize=False,
            strict=True,
        )
        names = [r['name'] for r in results]
        print('النتائج:', names)
        all_ok &= test_case('pizza ضمن النتائج', pizza.name_ar in names)
        all_ok &= test_case('mandi ليس في النتائج', mandi.name_ar not in names)

        pizza_result = next((r for r in results if r['name'] == pizza.name_ar), None)
        assert pizza_result, 'pizza result missing'

        print('\nالحقول المرجَّعة لـ pizza:')
        for key in ['subcategory', 'description', 'agent_notes', 'services',
                    'reviews_count', 'is_verified', 'name_en']:
            print(f'   {key}: {pizza_result.get(key)!r}')

        all_ok &= test_case('subcategory == "بيتزا"',
                            pizza_result.get('subcategory') == 'بيتزا')
        all_ok &= test_case('description كامل غير مقطوع (يطابق القيمة الأصلية)',
                            pizza_result.get('description') == pizza.description,
                            f"len={len(pizza_result.get('description') or '')}, "
                            f"orig={len(pizza.description)}")
        all_ok &= test_case('agent_notes موجودة',
                            'متخصص بالبيتزا' in (pizza_result.get('agent_notes') or ''))
        all_ok &= test_case('services قائمة غير فارغة',
                            isinstance(pizza_result.get('services'), list)
                            and 'توصيل' in pizza_result.get('services', []))
        all_ok &= test_case('reviews_count رقم صحيح',
                            pizza_result.get('reviews_count') == 210)

        print('\n' + '=' * 72)
        print('2) format_supplier_response يُظهر التفاصيل للوكيل')
        print('=' * 72)
        rendered = format_supplier_response(pizza_result)
        print(rendered)
        print()
        all_ok &= test_case('🏷️ التخصص: بيتزا', '🏷️' in rendered and 'بيتزا' in rendered)
        all_ok &= test_case('🛠️ الخدمات: توصيل', '🛠️' in rendered and 'توصيل' in rendered)
        all_ok &= test_case('📝 الوصف ظاهر', '📝' in rendered)
        all_ok &= test_case('💡 ملاحظات الوكيل ظاهرة', '💡' in rendered)
        all_ok &= test_case('⭐ تقييم + (210 تقييم)', '(210 تقييم)' in rendered)

        print('\n' + '=' * 72)
        print('3) البحث بكلمة تظهر فقط في agent_notes ("للعوائل")')
        print('=' * 72)
        results = search_suppliers(
            category_name='TEST-مطعم',
            keywords=['للعوائل'],
            limit=5,
            randomize=False,
            strict=True,
        )
        names = [r['name'] for r in results]
        print('النتائج:', names)
        all_ok &= test_case('pizza وُجد عبر agent_notes', pizza.name_ar in names)

        print('\n' + '=' * 72)
        print('4) البحث بكلمة تظهر فقط في description ("نباتية" → في services أيضاً)')
        print('=' * 72)
        results = search_suppliers(
            category_name='TEST-مطعم',
            keywords=['إيطالية'],
            limit=5,
            randomize=False,
            strict=True,
        )
        names = [r['name'] for r in results]
        print('النتائج:', names)
        all_ok &= test_case('pizza وُجد عبر description', pizza.name_ar in names)
        all_ok &= test_case('mandi لم يُرجَع (لا يذكر إيطالية)',
                            mandi.name_ar not in names)

        print('\n' + '=' * 72)
        print('5) البحث بـ subcategory مباشرة ("مندي") يجد mandi ويتجاهل pizza')
        print('=' * 72)
        results = search_suppliers(
            category_name='TEST-مطعم',
            keywords=['مندي'],
            limit=5,
            randomize=False,
            strict=True,
        )
        names = [r['name'] for r in results]
        print('النتائج:', names)
        all_ok &= test_case('mandi ضمن النتائج', mandi.name_ar in names)
        all_ok &= test_case('pizza ليس في النتائج', pizza.name_ar not in names)

        mandi_result = next((r for r in results if r['name'] == mandi.name_ar), None)
        all_ok &= test_case('mandi.subcategory == "مندي"',
                            mandi_result and mandi_result.get('subcategory') == 'مندي')

        print('\n' + '=' * 72)
        print('الخلاصة:', '✅ كل الاختبارات نجحت' if all_ok else '❌ بعض الاختبارات فشلت')
        print('=' * 72)
    finally:
        teardown_fixtures(cat, pizza, mandi)

    sys.exit(0 if all_ok else 1)


if __name__ == '__main__':
    main()
