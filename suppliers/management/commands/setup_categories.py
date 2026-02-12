"""
أمر إدارة لإنشاء التصنيفات الافتراضية
"""
from django.core.management.base import BaseCommand
from suppliers.models import Category


DEFAULT_CATEGORIES = [
    # مطاعم وطعام
    {'name_ar': 'مطعم', 'name_en': 'Restaurant', 'icon': 'bi-cup-straw'},
    {'name_ar': 'كافيه', 'name_en': 'Cafe', 'icon': 'bi-cup-hot'},
    {'name_ar': 'مخبز', 'name_en': 'Bakery', 'icon': 'bi-basket'},
    {'name_ar': 'حلويات', 'name_en': 'Sweets', 'icon': 'bi-cake'},
    {'name_ar': 'عصائر', 'name_en': 'Juice', 'icon': 'bi-cup'},
    
    # صحة
    {'name_ar': 'صيدلية', 'name_en': 'Pharmacy', 'icon': 'bi-capsule'},
    {'name_ar': 'مستشفى', 'name_en': 'Hospital', 'icon': 'bi-hospital'},
    {'name_ar': 'عيادة', 'name_en': 'Clinic', 'icon': 'bi-heart-pulse'},
    {'name_ar': 'طبيب أسنان', 'name_en': 'Dentist', 'icon': 'bi-emoji-smile'},
    {'name_ar': 'مختبر طبي', 'name_en': 'Medical Lab', 'icon': 'bi-droplet'},
    
    # خدمات منزلية
    {'name_ar': 'كهربائي', 'name_en': 'Electrician', 'icon': 'bi-lightning'},
    {'name_ar': 'سباك', 'name_en': 'Plumber', 'icon': 'bi-droplet-half'},
    {'name_ar': 'نجار', 'name_en': 'Carpenter', 'icon': 'bi-hammer'},
    {'name_ar': 'دهان', 'name_en': 'Painter', 'icon': 'bi-brush'},
    {'name_ar': 'حداد', 'name_en': 'Blacksmith', 'icon': 'bi-tools'},
    {'name_ar': 'مكيفات', 'name_en': 'AC Services', 'icon': 'bi-snow'},
    {'name_ar': 'نقل عفش', 'name_en': 'Moving', 'icon': 'bi-truck'},
    {'name_ar': 'تنظيف', 'name_en': 'Cleaning', 'icon': 'bi-stars'},
    
    # سيارات
    {'name_ar': 'ورشة سيارات', 'name_en': 'Car Repair', 'icon': 'bi-wrench'},
    {'name_ar': 'غسيل سيارات', 'name_en': 'Car Wash', 'icon': 'bi-droplet'},
    {'name_ar': 'محطة وقود', 'name_en': 'Gas Station', 'icon': 'bi-fuel-pump'},
    {'name_ar': 'كهرباء سيارات', 'name_en': 'Auto Electric', 'icon': 'bi-battery-charging'},
    {'name_ar': 'إطارات', 'name_en': 'Tires', 'icon': 'bi-circle'},
    
    # بنوك ومالية
    {'name_ar': 'بنك', 'name_en': 'Bank', 'icon': 'bi-bank'},
    {'name_ar': 'صراف آلي', 'name_en': 'ATM', 'icon': 'bi-credit-card'},
    {'name_ar': 'صرافة', 'name_en': 'Exchange', 'icon': 'bi-currency-exchange'},
    
    # تسوق
    {'name_ar': 'سوبرماركت', 'name_en': 'Supermarket', 'icon': 'bi-cart'},
    {'name_ar': 'بقالة', 'name_en': 'Grocery', 'icon': 'bi-bag'},
    {'name_ar': 'مول', 'name_en': 'Mall', 'icon': 'bi-shop'},
    {'name_ar': 'ملابس', 'name_en': 'Clothing', 'icon': 'bi-bag-heart'},
    {'name_ar': 'إلكترونيات', 'name_en': 'Electronics', 'icon': 'bi-phone'},
    {'name_ar': 'أثاث', 'name_en': 'Furniture', 'icon': 'bi-house'},
    
    # أماكن عامة
    {'name_ar': 'مسجد', 'name_en': 'Mosque', 'icon': 'bi-moon'},
    {'name_ar': 'مدرسة', 'name_en': 'School', 'icon': 'bi-book'},
    {'name_ar': 'جامعة', 'name_en': 'University', 'icon': 'bi-mortarboard'},
    {'name_ar': 'حديقة', 'name_en': 'Park', 'icon': 'bi-tree'},
    
    # سكن وفنادق
    {'name_ar': 'فندق', 'name_en': 'Hotel', 'icon': 'bi-building'},
    {'name_ar': 'شقق مفروشة', 'name_en': 'Furnished Apartments', 'icon': 'bi-house-door'},
    
    # ترفيه وجمال
    {'name_ar': 'صالة رياضية', 'name_en': 'Gym', 'icon': 'bi-bicycle'},
    {'name_ar': 'صالون تجميل', 'name_en': 'Beauty Salon', 'icon': 'bi-scissors'},
    {'name_ar': 'حلاق', 'name_en': 'Barber', 'icon': 'bi-scissors'},
    {'name_ar': 'سبا', 'name_en': 'Spa', 'icon': 'bi-flower1'},
    
    # خدمات أخرى
    {'name_ar': 'مصور', 'name_en': 'Photographer', 'icon': 'bi-camera'},
    {'name_ar': 'مدرس خصوصي', 'name_en': 'Tutor', 'icon': 'bi-person-video'},
    {'name_ar': 'محامي', 'name_en': 'Lawyer', 'icon': 'bi-briefcase'},
    {'name_ar': 'عقارات', 'name_en': 'Real Estate', 'icon': 'bi-houses'},
    
    # عام
    {'name_ar': 'عام', 'name_en': 'General', 'icon': 'bi-grid'},
]


class Command(BaseCommand):
    help = 'إنشاء التصنيفات الافتراضية'

    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0
        
        for i, cat_data in enumerate(DEFAULT_CATEGORIES):
            category, created = Category.objects.update_or_create(
                name_ar=cat_data['name_ar'],
                defaults={
                    'name_en': cat_data.get('name_en', ''),
                    'icon': cat_data.get('icon', ''),
                    'is_active': True,
                    'order': i
                }
            )
            
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'✅ Created: {cat_data["name_ar"]}'))
            else:
                updated_count += 1
                self.stdout.write(f'📝 Updated: {cat_data["name_ar"]}')
        
        self.stdout.write(self.style.SUCCESS(
            f'\n✅ Done! Created: {created_count}, Updated: {updated_count}, Total: {len(DEFAULT_CATEGORIES)}'
        ))
