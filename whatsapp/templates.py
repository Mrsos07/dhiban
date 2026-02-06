"""
قوالب رسائل WhatsApp
"""


class MessageTemplates:
    """قوالب الرسائل المعدة مسبقاً"""
    
    @staticmethod
    def welcome_template(user_name: str = '') -> dict:
        """قالب الترحيب"""
        return {
            "name": "welcome_message",
            "language": "ar",
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": user_name or "عزيزي العميل"}
                    ]
                }
            ]
        }
    
    @staticmethod
    def supplier_found_template(supplier_name: str, category: str) -> dict:
        """قالب إيجاد مورد"""
        return {
            "name": "supplier_found",
            "language": "ar",
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": supplier_name},
                        {"type": "text", "text": category}
                    ]
                }
            ]
        }
    
    @staticmethod
    def request_confirmation_template(request_id: str, category: str) -> dict:
        """قالب تأكيد الطلب"""
        return {
            "name": "request_confirmation",
            "language": "ar",
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": request_id[:8]},
                        {"type": "text", "text": category}
                    ]
                }
            ]
        }
    
    @staticmethod
    def no_results_template(search_query: str) -> dict:
        """قالب عدم وجود نتائج"""
        return {
            "name": "no_results",
            "language": "ar",
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": search_query}
                    ]
                }
            ]
        }


class QuickReplies:
    """ردود سريعة جاهزة"""
    
    MAIN_MENU = [
        {"id": "search", "title": " بحث"},
        {"id": "categories", "title": " التصنيفات"},
        {"id": "help", "title": " مساعدة"}
    ]
    
    SUPPLIER_ACTIONS = [
        {"id": "location", "title": " الموقع"},
        {"id": "call", "title": " اتصال"},
        {"id": "back", "title": " رجوع"}
    ]
    
    CONFIRMATION = [
        {"id": "yes", "title": " نعم"},
        {"id": "no", "title": " لا"}
    ]
    
    RATING = [
        {"id": "rate_5", "title": ""},
        {"id": "rate_3", "title": ""},
        {"id": "rate_1", "title": ""}
    ]


class ResponseMessages:
    """رسائل الاستجابة"""
    
    WELCOME = "مرحباً بك في ذيبان! \nأنا دليلك الذكي للوصول إلى أي مكان أو خدمة."
    
    ASK_SEARCH = "أرسل لي ما تبحث عنه وسأساعدك في إيجاده."
    
    NO_RESULTS = "عذراً، لم نجد نتائج مطابقة لبحثك. جرب كلمات أخرى."
    
    ERROR = "عذراً، حدث خطأ. يرجى المحاولة مرة أخرى."
    
    THANK_YOU = "شكراً لاستخدامك ذيبان! "
    
    HELP = '''
 *كيف أستخدم ذيبان؟*

1 أرسل اسم المكان أو الخدمة
2 اختر من النتائج
3 احصل على التفاصيل والموقع

 للمساعدة أرسل: مساعدة
'''
    
    @staticmethod
    def search_results(count: int) -> str:
        if count == 0:
            return ResponseMessages.NO_RESULTS
        elif count == 1:
            return "وجدنا نتيجة واحدة:"
        else:
            return f"وجدنا {count} نتيجة. اختر أحدها:"
    
    @staticmethod
    def supplier_details(supplier: dict) -> str:
        return f'''
 *{supplier.get('name', '')}*

 التصنيف: {supplier.get('category', '')}
 التقييم: {supplier.get('rating', 0)}/5
 الهاتف: {supplier.get('phone', 'غير متوفر')}
 ساعات العمل: {supplier.get('hours', 'غير محدد')}

{supplier.get('description', '')}
'''.strip()
