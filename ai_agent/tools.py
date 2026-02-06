"""
أدوات البحث عن الموردين والأماكن
"""
import json
from typing import List, Dict, Optional
from django.db.models import Q
from suppliers.models import Supplier, Category
from .places import search_nearby_places, get_place_details, format_google_place
from .intents import detect_intent, IntentType, should_search_database, should_search_google


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
        results.append({
            'id': str(supplier.id),
            'name': supplier.name_ar,
            'category': supplier.category.name_ar if supplier.category else '',
            'rating': float(supplier.rating),
            'phone': supplier.get_primary_phone() or '',
            'location': supplier.location,
            'is_partner': supplier.is_partner,
            'description': supplier.description[:100] if supplier.description else '',
            'source': 'database'
        })
    
    return results


def search_google_places(
    query: str,
    place_type: Optional[str] = None,
    limit: int = 3
) -> List[Dict]:
    """
    البحث في Google Maps
    """
    places = search_nearby_places(query=query, place_type=place_type)
    
    results = []
    for place in places[:limit]:
        results.append({
            'id': place.get('place_id', ''),
            'name': place.get('name', ''),
            'category': ', '.join(place.get('types', [])[:2]),
            'rating': place.get('rating', 0),
            'phone': '',
            'location': place.get('location', {}),
            'address': place.get('address', ''),
            'is_open': place.get('is_open'),
            'source': 'google'
        })
    
    return results


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


def format_supplier_response(supplier: Dict) -> str:
    """تنسيق رد المورد للمستخدم"""
    response = f"""
 *{supplier.get('name', '')}*
 التصنيف: {supplier.get('category', '')}
 التقييم: {supplier.get('rating', 0)}/5
"""
    
    if supplier.get('phone'):
        response += f" الهاتف: {supplier['phone']}\n"
    
    if supplier.get('address'):
        response += f" العنوان: {supplier['address']}\n"
    elif supplier.get('location', {}).get('address'):
        response += f" العنوان: {supplier['location']['address']}\n"
    
    if supplier.get('is_partner'):
        response += " شريك معتمد\n"
    
    if supplier.get('is_open') is not None:
        status = "مفتوح الآن " if supplier['is_open'] else "مغلق "
        response += f" {status}\n"
    
    return response.strip()


def format_search_results(results: Dict, query: str = "") -> str:
    """تنسيق نتائج البحث المدمجة"""
    db_results = results.get('database_results', [])
    google_results = results.get('google_results', [])
    
    if not db_results and not google_results:
        return f"عذرا لم أجد نتائج لـ '{query}'. جرب وصفا مختلفا أو تصنيفا آخر."
    
    response = f" وجدت لك {results['total']} نتيجة:\n\n"
    
    # نتائج قاعدة البيانات (الموردين المسجلين)
    if db_results:
        response += " *من شركائنا:*\n\n"
        for i, supplier in enumerate(db_results, 1):
            response += f"{i}. {format_supplier_response(supplier)}\n\n"
    
    # نتائج Google Maps
    if google_results:
        response += " *من Google Maps:*\n\n"
        start_num = len(db_results) + 1
        for i, place in enumerate(google_results, start_num):
            response += f"{i}. {format_supplier_response(place)}\n\n"
    
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
    }
]
