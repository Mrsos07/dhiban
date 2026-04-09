"""
أدوات البحث عن الموردين والأماكن
"""
import json
import logging
from typing import List, Dict, Optional
from django.db.models import Q
from suppliers.models import Supplier, Category
from .places import search_nearby_places, get_place_details, format_google_place
from .intents import (
    detect_intent, IntentType, ConversationState,
    should_search_database, should_search_google,
    is_tourism_intent, is_chat_only, is_immediate_search,
    needs_followup, get_plan_activities,
    ACTIVITY_CATEGORIES, PLAN_TEMPLATES, TOURISM_INTENTS,
    CHAT_ONLY_INTENTS, IMMEDIATE_SEARCH_INTENTS,
)

logger = logging.getLogger(__name__)


def search_suppliers(
    category_name: Optional[str] = None,
    keywords: Optional[List[str]] = None,
    is_partner: Optional[bool] = None,
    limit: int = 5
) -> List[Dict]:
    """
    البحث عن الموردين في قاعدة البيانات
    """
    queryset = Supplier.objects.filter(is_active=True)
    
    if category_name:
        queryset = queryset.filter(
            Q(category__name_ar__icontains=category_name) |
            Q(category__name_en__icontains=category_name) |
            Q(subcategory__name_ar__icontains=category_name)
        )
    
    if keywords:
        keyword_filter = Q()
        for keyword in keywords:
            keyword_filter |= (
                Q(name_ar__icontains=keyword) |
                Q(name_en__icontains=keyword) |
                Q(description__icontains=keyword) |
                Q(services__icontains=keyword)
            )
        queryset = queryset.filter(keyword_filter)
    
    if is_partner is not None:
        queryset = queryset.filter(is_partner=is_partner)
    
    queryset = queryset.order_by('-is_partner', '-rating')[:limit]
    
    results = []
    for supplier in queryset:
        import urllib.parse
        # بناء رابط الموقع — الإحداثيات أولاً لأنها أقصر
        maps_url = ''
        if supplier.location and supplier.location.get('lat') and supplier.location.get('lng'):
            lat = supplier.location.get('lat')
            lng = supplier.location.get('lng')
            maps_url = f"https://maps.google.com/?q={lat},{lng}"
        elif hasattr(supplier, 'google_maps_url') and supplier.google_maps_url:
            maps_url = supplier.google_maps_url
        else:
            # fallback: بحث بالاسم في عنيزة
            name = supplier.name_ar or supplier.name_en or ''
            if name:
                q = urllib.parse.quote(f"{name} عنيزة")
                maps_url = f"https://maps.google.com/maps?q={q}"
        
        results.append({
            'id': str(supplier.id),
            'name': supplier.name_ar,
            'category': supplier.category.name_ar if supplier.category else '',
            'rating': float(supplier.rating),
            'phone': supplier.get_primary_phone() or '',
            'location': supplier.location,
            'maps_url': maps_url,
            'is_partner': supplier.is_partner,
            'description': supplier.description[:100] if supplier.description else '',
            'source': 'database'
        })
    
    return results


def get_category_from_google_type(primary_type: str, types: list, search_query: str = None) -> str:
    """
    تحويل نوع Google إلى تصنيف عربي
    """
    # خريطة الأنواع من Google إلى العربية
    TYPE_MAPPING = {
        # مطاعم وطعام
        'restaurant': 'مطعم',
        'cafe': 'كافيه',
        'bakery': 'مخبز',
        'meal_takeaway': 'مطعم',
        'meal_delivery': 'مطعم توصيل',
        'fast_food_restaurant': 'مطعم وجبات سريعة',
        'coffee_shop': 'كافيه',
        'ice_cream_shop': 'آيس كريم',
        'juice_shop': 'عصائر',
        
        # صحة
        'pharmacy': 'صيدلية',
        'hospital': 'مستشفى',
        'doctor': 'عيادة',
        'dentist': 'طبيب أسنان',
        'health': 'صحة',
        'medical_lab': 'مختبر طبي',
        
        # خدمات
        'electrician': 'كهربائي',
        'plumber': 'سباك',
        'car_repair': 'ورشة سيارات',
        'car_wash': 'غسيل سيارات',
        'gas_station': 'محطة وقود',
        'atm': 'صراف آلي',
        'bank': 'بنك',
        
        # تسوق
        'supermarket': 'سوبرماركت',
        'grocery_store': 'بقالة',
        'shopping_mall': 'مول',
        'clothing_store': 'ملابس',
        'electronics_store': 'إلكترونيات',
        'furniture_store': 'أثاث',
        'hardware_store': 'أدوات',
        
        # أماكن عامة
        'mosque': 'مسجد',
        'school': 'مدرسة',
        'university': 'جامعة',
        'gym': 'صالة رياضية',
        'park': 'حديقة',
        'hotel': 'فندق',
        'lodging': 'سكن',
        
        # ترفيه
        'movie_theater': 'سينما',
        'spa': 'سبا',
        'beauty_salon': 'صالون تجميل',
        'hair_salon': 'حلاق',
        'barber_shop': 'حلاق',
    }
    
    # البحث في النوع الرئيسي أولاً
    if primary_type and primary_type in TYPE_MAPPING:
        return TYPE_MAPPING[primary_type]
    
    # البحث في الأنواع الأخرى
    for t in types:
        if t in TYPE_MAPPING:
            return TYPE_MAPPING[t]
    
    # استخدام كلمة البحث إذا لم نجد
    if search_query:
        # تنظيف كلمة البحث
        clean_query = search_query.strip()
        if clean_query in ['شاورما', 'برقر', 'بيتزا', 'بروستد', 'كبسة', 'مندي']:
            return 'مطعم'
        return clean_query
    
    return 'عام'


def save_google_place_as_supplier(place: Dict, category_name: str = None) -> Optional[Supplier]:
    """
    حفظ مكان من Google Maps كمورد في قاعدة البيانات
    مع جميع التفاصيل المتاحة
    """
    try:
        place_id = place.get('place_id') or place.get('maps_url', '')
        name = place.get('name', '')
        
        if not name:
            return None
        
        # التحقق من وجود المورد مسبقاً (بالاسم أو place_id)
        existing = Supplier.objects.filter(
            Q(name_ar=name) | Q(google_maps_place_id=place_id)
        ).first()
        
        if existing:
            # تحديث البيانات إذا تغيرت
            updated_fields = []
            
            new_rating = place.get('rating', 0)
            new_reviews = place.get('total_ratings', 0)
            new_phone = place.get('phone', '')
            
            if new_rating and new_rating != float(existing.rating):
                existing.rating = new_rating
                updated_fields.append('rating')
            
            if new_reviews and new_reviews != existing.reviews_count:
                existing.reviews_count = new_reviews
                updated_fields.append('reviews_count')
            
            # تحديث الهاتف إذا كان فارغاً
            if new_phone and not existing.phone_numbers:
                existing.phone_numbers = [new_phone]
                updated_fields.append('phone_numbers')
            
            # تحديث الموقع إذا كان فارغاً
            if place.get('website') and not existing.website:
                existing.website = place.get('website')
                updated_fields.append('website')
            
            # تحديث رابط الخريطة إذا كان فارغاً
            if place.get('maps_url') and not existing.google_maps_url:
                existing.google_maps_url = place.get('maps_url')
                updated_fields.append('google_maps_url')
            
            if updated_fields:
                updated_fields.append('updated_at')
                existing.save(update_fields=updated_fields)
                logger.info(f"Updated supplier: {name} - fields: {updated_fields}")
            
            return existing
        
        # تحديد التصنيف من نوع Google أو كلمة البحث
        detected_category = get_category_from_google_type(
            place.get('primary_type', ''),
            place.get('types', []),
            category_name
        )
        
        # البحث عن التصنيف أو إنشاؤه
        category, created = Category.objects.get_or_create(
            name_ar=detected_category,
            defaults={'is_active': True}
        )
        if created:
            logger.info(f"Created new category: {detected_category}")
        
        # تجهيز أرقام الهواتف
        phone_numbers = []
        if place.get('phone'):
            phone_numbers = [place.get('phone')]
        
        # تجهيز ساعات العمل
        working_hours = place.get('working_hours', {})
        
        # إنشاء المورد الجديد
        supplier = Supplier.objects.create(
            name_ar=name,
            category=category,
            rating=place.get('rating', 0),
            reviews_count=place.get('total_ratings', 0),
            google_maps_place_id=place_id,
            google_maps_url=place.get('maps_url', ''),
            location={
                'lat': place.get('location', {}).get('lat', 0),
                'lng': place.get('location', {}).get('lng', 0),
                'address': place.get('address', '')
            },
            phone_numbers=phone_numbers,
            website=place.get('website', ''),
            working_hours=working_hours,
            is_active=True,
            is_verified=False,
            is_partner=False
        )
        
        logger.info(f"Saved new supplier from Google: {name} | {detected_category} | ⭐{place.get('rating', 0)} | 📞{place.get('phone', 'N/A')}")
        return supplier
        
    except Exception as e:
        logger.error(f"Error saving Google place as supplier: {e}")
        return None


def search_google_places(
    query: str,
    place_type: Optional[str] = None,
    limit: int = 5,
    save_results: bool = True,
    category_name: str = None
) -> List[Dict]:
    """
    البحث في Google Maps عن أماكن في عنيزة
    النتائج مرتبة حسب التقييم
    يتم حفظ النتائج تلقائياً في قاعدة البيانات
    """
    places = search_nearby_places(query=query, place_type=place_type, max_results=limit)
    
    results = []
    for place in places:
        result = {
            'name': place.get('name', ''),
            'rating': place.get('rating', 0),
            'total_ratings': place.get('total_ratings', 0),
            'address': place.get('address', ''),
            'location': place.get('location', {}),
            'is_open': place.get('is_open'),
            'maps_url': place.get('maps_url', ''),
            'place_id': place.get('place_id', ''),
            'phone': place.get('phone', ''),
            'website': place.get('website', ''),
            'types': place.get('types', []),
            'primary_type': place.get('primary_type', ''),
            'working_hours': place.get('working_hours', {}),
            'source': 'google'
        }
        results.append(result)
        
        # حفظ النتيجة في قاعدة البيانات
        if save_results:
            save_google_place_as_supplier(result, category_name or query)
    
    return results


def format_google_results(places: List[Dict], query: str = "") -> str:
    """تنسيق نتائج البحث من Google Maps"""
    if not places:
        return f"ما لقيت '{query}' في عنيزة 😕"
    
    response = f"🔍 هذي أحسن الخيارات لـ '{query}':\n\n"
    
    for i, place in enumerate(places[:2], 1):
        name = place.get('name', 'غير معروف')
        rating = place.get('rating', 0)
        total_ratings = place.get('total_ratings', 0)
        address = place.get('address', '')
        is_open = place.get('is_open')
        phone = place.get('phone', '')
        
        open_status = "✅ مفتوح" if is_open else ("❌ مغلق" if is_open is False else "")
        maps_url = build_maps_url(place)
        
        response += f"{i}. *{name}*\n"
        if rating:
            response += f"   ⭐ {rating}/5 ({total_ratings} تقييم)\n"
        if address:
            response += f"   📍 {address}\n"
        if phone:
            response += f"   📞 {phone}\n"
        if open_status:
            response += f"   🕐 {open_status}\n"
        if maps_url:
            response += f"   🗺️ الموقع:\n{maps_url}\n"
        response += "\n"
    
    response += "تبي شي ثاني؟ 🐺"
    return response.strip()


def combined_search(
    query: str,
    category: Optional[str] = None,
    keywords: Optional[List[str]] = None
) -> Dict:
    """
    بحث مدمج في قاعدة البيانات و Google Maps
    """
    results = {
        'database_results': [],
        'google_results': [],
        'total': 0
    }
    
    # البحث في قاعدة البيانات أولا
    db_results = search_suppliers(
        category_name=category,
        keywords=keywords or [query],
        limit=5
    )
    results['database_results'] = db_results
    
    # إذا لم نجد نتائج كافية نبحث في Google
    if len(db_results) < 3:
        google_results = search_google_places(query=query, limit=3)
        results['google_results'] = google_results
    
    results['total'] = len(db_results) + len(results['google_results'])
    
    return results


def get_categories() -> List[Dict]:
    """الحصول على قائمة التصنيفات"""
    categories = Category.objects.filter(is_active=True)
    return [
        {
            'id': str(cat.id),
            'name_ar': cat.name_ar,
            'name_en': cat.name_en or '',
        }
        for cat in categories
    ]


def build_maps_url(supplier: Dict) -> str:
    """
    بناء رابط Google Maps يعمل بشكل صحيح في واتساب.
    الأولوية: googleMapsUri > إحداثيات > بحث بالاسم.
    يستخدم الصيغة الرسمية: https://www.google.com/maps/search/?api=1&query=...
    """
    import urllib.parse
    # 1. رابط Google Maps الرسمي من API (أفضل خيار — يفتح المكان مباشرة)
    url = supplier.get('maps_url') or supplier.get('google_maps_url', '')
    if url and url.startswith('http'):
        return url
    # 2. إحداثيات lat/lng — رابط رسمي يعمل في واتساب
    loc = supplier.get('location', {})
    lat = loc.get('lat') if isinstance(loc, dict) else None
    lng = loc.get('lng') if isinstance(loc, dict) else None
    if lat and lng:
        return f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"
    # 3. fallback — بحث بالاسم
    name = supplier.get('name', '')
    if name:
        query = urllib.parse.quote(f"{name} عنيزة")
        return f"https://www.google.com/maps/search/?api=1&query={query}"
    return ''


def format_supplier_response(supplier: Dict) -> str:
    """تنسيق رد المورد للمستخدم"""
    response = f"*{supplier.get('name', '')}*\n"
    response += f"   ⭐ {supplier.get('rating', 0)}/5\n"
    
    if supplier.get('phone'):
        response += f"   📞 {supplier['phone']}\n"
    
    address = supplier.get('address', '')
    if not address:
        loc = supplier.get('location', {})
        address = loc.get('address', '') if isinstance(loc, dict) else ''
    if address:
        response += f"   📍 {address}\n"
    
    if supplier.get('is_partner'):
        response += "   ✅ شريك معتمد\n"
    
    if supplier.get('is_open') is not None:
        status = "✅ مفتوح" if supplier['is_open'] else "❌ مغلق"
        response += f"   🕐 {status}\n"
    
    # رابط الخريطة — على سطر منفصل لكي يعمل في واتساب
    maps_url = build_maps_url(supplier)
    if maps_url:
        response += f"   🗺️ الموقع:\n{maps_url}\n"
    
    return response.strip()


def build_daily_plan(
    activities: Optional[List[str]] = None,
    plan_type: str = 'daily',
    preferences: Optional[str] = None
) -> str:
    """
    بناء خطة يومية سياحية مع روابط Google Maps لكل مكان
    
    Args:
        activities: قائمة الأنشطة المطلوبة مثل ['coffee', 'walk', 'food']
        plan_type: نوع الخطة (daily/evening/morning/weekend)
        preferences: تفضيلات إضافية من المستخدم
    """
    if not activities:
        activities = ['coffee', 'walk', 'food']
    
    # أوقات تقريبية حسب نوع الخطة
    time_slots = {
        'morning': [
            ('☀️ 7:00 - 8:30', 'فطور'),
            ('🌤️ 9:00 - 10:30', 'تمشية/نشاط'),
            ('☕ 11:00 - 12:00', 'قهوة/استراحة'),
        ],
        'evening': [
            ('🌅 4:00 - 5:30', 'قهوة/بداية'),
            ('🚶 5:30 - 7:00', 'تمشية/نشاط'),
            ('🍽️ 7:30 - 9:00', 'عشاء'),
        ],
        'daily': [
            ('☀️ 8:00 - 9:30', 'فطور'),
            ('🌤️ 10:00 - 11:30', 'نشاط صباحي'),
            ('🍽️ 12:30 - 2:00', 'غداء'),
            ('☕ 4:00 - 5:30', 'قهوة/استراحة'),
            ('🌙 7:00 - 9:00', 'عشاء/سهرة'),
        ],
        'weekend': [
            ('☀️ 8:00 - 9:30', 'فطور'),
            ('🏛️ 10:00 - 12:00', 'استكشاف/زيارة'),
            ('🍽️ 12:30 - 2:00', 'غداء'),
            ('🚶 3:30 - 5:00', 'تمشية'),
            ('☕ 5:00 - 6:30', 'قهوة'),
            ('🌙 7:30 - 9:30', 'عشاء/سهرة'),
        ],
    }
    
    # اختيار الأوقات حسب نوع الخطة
    slots = time_slots.get(plan_type, time_slots['daily'])
    
    # تقليم الأنشطة لتتناسب مع عدد الأوقات
    plan_activities = activities[:len(slots)]
    
    # بناء الخطة
    response = "📋 *خطتك اليومية في عنيزة* 🐺\n"
    response += "═" * 30 + "\n\n"
    
    step_num = 1
    seen_places = set()  # لتجنب تكرار الأماكن
    
    for i, activity_key in enumerate(plan_activities):
        activity_info = ACTIVITY_CATEGORIES.get(activity_key)
        if not activity_info:
            continue
        
        # اختيار الوقت
        time_slot = slots[i] if i < len(slots) else slots[-1]
        time_str, time_label = time_slot
        
        # البحث عن مكان مناسب
        search_query = activity_info['search_queries'][0]
        places = search_google_places(
            query=search_query,
            place_type=activity_info['google_types'][0] if activity_info['google_types'] else None,
            limit=3,
            save_results=True
        )
        
        # اختيار أفضل مكان غير مكرر
        selected_place = None
        for place in places:
            place_name = place.get('name', '')
            if place_name not in seen_places:
                selected_place = place
                seen_places.add(place_name)
                break
        
        if not selected_place and places:
            selected_place = places[0]
        
        # تنسيق الخطوة
        response += f"*{step_num}. {time_str} — {activity_info['label']}*\n"
        
        if selected_place:
            name = selected_place.get('name', 'مكان مميز')
            rating = selected_place.get('rating', 0)
            address = selected_place.get('address', '')
            maps_url = build_maps_url(selected_place)
            
            response += f"   📍 *{name}*\n"
            if rating:
                response += f"   ⭐ {rating}/5\n"
            if address:
                response += f"   🏠 {address}\n"
            if maps_url:
                response += f"   🗺️ الموقع:\n{maps_url}\n"
        else:
            response += f"   📍 ابحث عن أفضل {activity_info['label']} في عنيزة\n"
        
        response += "\n"
        step_num += 1
    
    response += "═" * 30 + "\n"
    response += "\n🐺 استمتع بيومك! تبي تعديل على الخطة؟"
    
    return response.strip()


def format_search_results(results: Dict, query: str = "") -> str:
    """تنسيق نتائج البحث المدمجة"""
    db_results = results.get('database_results', [])
    google_results = results.get('google_results', [])
    
    if not db_results and not google_results:
        return f"ما لقيت '{query}' في عنيزة 😕\nجرب شي ثاني!"
    
    response = f"🔍 هذي أحسن الخيارات لـ '{query}':\n\n"
    
    # نتائج قاعدة البيانات (الموردين المسجلين) - أفضل 2 فقط
    count = 0
    if db_results:
        for i, supplier in enumerate(db_results[:2], 1):
            response += f"{i}. {format_supplier_response(supplier)}\n\n"
            count = i
    
    # نتائج Google Maps - إذا لم نجد في الموردين
    if google_results and count < 2:
        for i, place in enumerate(google_results[:2-count], count + 1):
            response += f"{i}. {format_supplier_response(place)}\n\n"
    
    response += "تبي شي ثاني؟ 🐺"
    return response.strip()


# تعريف الأدوات لـ OpenAI Function Calling
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_suppliers",
            "description": "البحث عن موردين أو مقدمي خدمات في قاعدة بيانات ذيبان",
            "parameters": {
                "type": "object",
                "properties": {
                    "category_name": {
                        "type": "string",
                        "description": "اسم التصنيف مثل: كهربائي سباك مطعم صيدلية"
                    },
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "كلمات البحث"
                    },
                    "is_partner": {
                        "type": "boolean",
                        "description": "البحث في الشركاء المعتمدين فقط"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_google_places",
            "description": "البحث عن أماكن في Google Maps في منطقة عنيزة",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "نص البحث"
                    },
                    "place_type": {
                        "type": "string",
                        "description": "نوع المكان مثل: restaurant, pharmacy, hospital"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "combined_search",
            "description": "بحث شامل في قاعدة البيانات و Google Maps معا",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "نص البحث الرئيسي"
                    },
                    "category": {
                        "type": "string",
                        "description": "التصنيف إن وجد"
                    },
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "كلمات إضافية للبحث"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_categories",
            "description": "الحصول على قائمة التصنيفات المتاحة",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "build_daily_plan",
            "description": "بناء خطة يومية سياحية كاملة مع روابط Google Maps لكل مكان. استخدم هذه الأداة عندما يطلب المستخدم خطة يومية أو اقتراح أنشطة أو وش يسوي اليوم أو يبي يطلع أو خروجة مع العائلة/الأصحاب",
            "parameters": {
                "type": "object",
                "properties": {
                    "activities": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["food", "coffee", "walk", "shopping", "entertainment", "culture", "nature", "kids", "dessert", "breakfast", "lunch", "dinner"]
                        },
                        "description": "قائمة الأنشطة المطلوبة بالترتيب. مثال: ['coffee', 'walk', 'dinner'] أو ['breakfast', 'culture', 'lunch', 'coffee', 'dinner']"
                    },
                    "plan_type": {
                        "type": "string",
                        "enum": ["daily", "morning", "evening", "weekend"],
                        "description": "نوع الخطة: daily=يوم كامل، morning=صباحية، evening=مسائية، weekend=نهاية أسبوع"
                    },
                    "preferences": {
                        "type": "string",
                        "description": "تفضيلات إضافية من المستخدم مثل: عائلي، شبابي، رومانسي، أطفال"
                    }
                },
                "required": ["activities", "plan_type"]
            }
        }
    }
]
