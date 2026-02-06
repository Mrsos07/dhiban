"""
نظام النوايا (Intent Recognition)
لفهم طلبات المستخدمين وتصنيفها
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class IntentType(Enum):
    """أنواع النوايا"""
    SEARCH_SERVICE = "search_service"      # البحث عن خدمة (كهربائي سباك)
    SEARCH_PLACE = "search_place"          # البحث عن مكان (مطعم صيدلية)
    GET_DIRECTIONS = "get_directions"      # طلب اتجاهات
    GET_INFO = "get_info"                  # طلب معلومات
    GREETING = "greeting"                  # تحية
    HELP = "help"                          # طلب مساعدة
    FEEDBACK = "feedback"                  # ملاحظات
    COMPLAINT = "complaint"                # شكوى
    UNKNOWN = "unknown"                    # غير معروف


@dataclass
class Intent:
    """كائن النية"""
    type: IntentType
    confidence: float
    entities: Dict
    original_text: str


# قاموس الكلمات المفتاحية لكل نية
INTENT_KEYWORDS = {
    IntentType.GREETING: [
        'مرحبا', 'السلام عليكم', 'هلا', 'اهلا', 'صباح الخير', 'مساء الخير',
        'hi', 'hello', 'hey', 'ابدأ', 'start'
    ],
    IntentType.HELP: [
        'مساعدة', 'help', 'كيف', 'شرح', 'ايش اسوي', 'وش اسوي', 'قائمة'
    ],
    IntentType.SEARCH_SERVICE: [
        'ابي', 'أبي', 'ابغى', 'أبغى', 'اريد', 'أريد', 'احتاج', 'أحتاج',
        'ابحث', 'دور لي', 'جيب لي', 'وين القى', 'وين الاقي'
    ],
    IntentType.SEARCH_PLACE: [
        'وين', 'فين', 'اقرب', 'أقرب', 'قريب', 'مكان', 'محل', 'موقع'
    ],
    IntentType.GET_DIRECTIONS: [
        'كيف اروح', 'كيف أروح', 'الطريق', 'اتجاهات', 'خريطة', 'موقع'
    ],
    IntentType.FEEDBACK: [
        'شكرا', 'شكرا', 'ممتاز', 'رائع', 'حلو', 'thanks', 'thank you'
    ],
    IntentType.COMPLAINT: [
        'شكوى', 'مشكلة', 'سيء', 'ما عجبني', 'زفت'
    ],
}

# قاموس التصنيفات والكلمات المرتبطة
CATEGORY_KEYWORDS = {
    'كهربائي': ['كهربائي', 'كهرباء', 'إنارة', 'انارة', 'لمبات', 'توصيلات', 'فيش', 'سلك'],
    'سباك': ['سباك', 'سباكة', 'مواسير', 'حنفية', 'مغسلة', 'صرف', 'تسليك'],
    'نجار': ['نجار', 'نجارة', 'خشب', 'باب', 'ابواب', 'دولاب', 'مطبخ'],
    'مطعم': ['مطعم', 'مطاعم', 'اكل', 'أكل', 'طعام', 'وجبة', 'غداء', 'عشاء', 'فطور'],
    'مقهى': ['مقهى', 'كافيه', 'قهوة', 'كوفي', 'cafe', 'coffee'],
    'صيدلية': ['صيدلية', 'دواء', 'ادوية', 'أدوية', 'علاج'],
    'ورشة': ['ورشة', 'سيارة', 'سيارات', 'ميكانيكي', 'صيانة', 'تصليح'],
    'بقالة': ['بقالة', 'سوبرماركت', 'ماركت', 'تموينات'],
    'مستشفى': ['مستشفى', 'مستوصف', 'عيادة', 'طبيب', 'دكتور'],
    'بنك': ['بنك', 'صراف', 'atm', 'تحويل'],
    'محل جوالات': ['جوال', 'جوالات', 'موبايل', 'هاتف', 'شاشة', 'تصليح جوال'],
    'حلاق': ['حلاق', 'صالون', 'حلاقة', 'قص شعر'],
    'غسيل سيارات': ['غسيل', 'غسيل سيارات', 'تلميع'],
}


def extract_entities(text: str) -> Dict:
    """استخراج الكيانات من النص"""
    entities = {
        'category': None,
        'location': None,
        'keywords': []
    }
    
    text_lower = text.lower()
    
    # البحث عن التصنيف
    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text_lower:
                entities['category'] = category
                entities['keywords'].append(keyword)
                break
        if entities['category']:
            break
    
    # البحث عن الموقع
    location_keywords = ['في', 'بـ', 'قريب من', 'جنب', 'حي']
    for loc_kw in location_keywords:
        if loc_kw in text_lower:
            # يمكن تحسين هذا لاستخراج اسم الحي
            pass
    
    return entities


def detect_intent(text: str) -> Intent:
    """
    اكتشاف نية المستخدم من النص
    
    Args:
        text: نص المستخدم
    
    Returns:
        كائن Intent
    """
    text_lower = text.lower().strip()
    
    # التحقق من كل نوع نية
    intent_scores = {}
    
    for intent_type, keywords in INTENT_KEYWORDS.items():
        score = 0
        for keyword in keywords:
            if keyword in text_lower:
                score += 1
        intent_scores[intent_type] = score
    
    # تحديد النية الأعلى
    max_score = max(intent_scores.values())
    
    if max_score == 0:
        # إذا لم نجد كلمات مفتاحية نفترض أنه بحث
        detected_intent = IntentType.SEARCH_SERVICE
        confidence = 0.5
    else:
        detected_intent = max(intent_scores, key=intent_scores.get)
        confidence = min(max_score / 3, 1.0)
    
    # استخراج الكيانات
    entities = extract_entities(text)
    
    # إذا وجدنا تصنيف نرفع الثقة
    if entities['category']:
        confidence = min(confidence + 0.3, 1.0)
    
    return Intent(
        type=detected_intent,
        confidence=confidence,
        entities=entities,
        original_text=text
    )


def get_intent_response_template(intent: Intent) -> str:
    """الحصول على قالب الرد حسب النية"""
    templates = {
        IntentType.GREETING: "مرحبا! أنا ذيبان  دليلك الذكي في عنيزة. كيف أقدر أساعدك",
        IntentType.HELP: "أقدر أساعدك في:\n- البحث عن خدمات (كهربائي سباك...)\n- إيجاد أماكن (مطاعم صيدليات...)\n- معرفة الاتجاهات\n\nفقط قل لي وش تحتاج!",
        IntentType.FEEDBACK: "شكرا لك!  سعيد إني قدرت أساعدك. لا تتردد تسألني أي وقت!",
        IntentType.COMPLAINT: "آسف على الإزعاج  أخبرني بالمشكلة وراح أحاول أساعدك.",
        IntentType.UNKNOWN: "ما فهمت طلبك تماما. ممكن توضح أكثر أو أرسل 'مساعدة' لمعرفة كيف أقدر أساعدك.",
    }
    
    return templates.get(intent.type, "")


def should_search_database(intent: Intent) -> bool:
    """هل يجب البحث في قاعدة البيانات"""
    return intent.type in [
        IntentType.SEARCH_SERVICE,
        IntentType.SEARCH_PLACE,
        IntentType.GET_INFO
    ]


def should_search_google(intent: Intent) -> bool:
    """هل يجب البحث في Google Maps"""
    return intent.type in [
        IntentType.SEARCH_PLACE,
        IntentType.GET_DIRECTIONS
    ]
