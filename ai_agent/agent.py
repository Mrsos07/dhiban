"""
وكيل الذكاء الاصطناعي الرئيسي
مع تكامل Google Maps ونظام النوايا
"""
import json
import logging
from typing import Optional, Dict, List
from openai import OpenAI
from django.conf import settings

from .config import OPENAI_API_KEY, OPENAI_MODEL
from .prompts import DHIBAN_SYSTEM_PROMPT
from .tools import (
    search_suppliers, search_google_places, combined_search,
    get_categories, format_search_results, format_google_results, TOOLS
)
from .intents import (
    detect_intent, IntentType, get_intent_response_template,
    should_search_google, should_search_database, get_search_query
)

logger = logging.getLogger(__name__)


class DhibanAgent:
    """
    وكيل ذيبان - الدليل الذكي لعنيزة
    مع تكامل قاعدة البيانات و Google Maps ونظام النوايا
    """
    
    # عدد الرسائل المحفوظة في الذاكرة
    MEMORY_SIZE = 5
    
    def __init__(self):
        self.client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
        self.model = OPENAI_MODEL
    
    def _get_conversation_history(self, user_id: str) -> List[Dict]:
        """جلب آخر 5 رسائل من المحادثة"""
        if not user_id:
            return []
        
        try:
            from conversations.models import Conversation
            from users.models import WhatsAppUser
            
            # البحث عن المستخدم
            user = WhatsAppUser.objects.filter(phone_number=user_id).first()
            if not user:
                return []
            
            # جلب آخر محادثة نشطة
            conversation = Conversation.objects.filter(
                user=user,
                ended_at__isnull=True
            ).order_by('-started_at').first()
            
            if not conversation or not conversation.messages:
                return []
            
            # جلب آخر 5 رسائل وتحويلها لصيغة OpenAI
            recent_messages = conversation.messages[-self.MEMORY_SIZE:]
            history = []
            for msg in recent_messages:
                role = "user" if msg.get('role') == 'user' else "assistant"
                history.append({
                    "role": role,
                    "content": msg.get('content', '')
                })
            
            return history
        
        except Exception as e:
            logger.error(f"Error getting conversation history: {e}")
            return []
    
    def _save_message(self, user_id: str, role: str, content: str):
        """حفظ الرسالة في المحادثة"""
        if not user_id:
            return
        
        try:
            from conversations.models import Conversation
            from users.models import WhatsAppUser
            from django.utils import timezone
            
            # البحث عن المستخدم أو إنشاؤه
            user, _ = WhatsAppUser.objects.get_or_create(
                phone_number=user_id,
                defaults={'name': f'User {user_id[-4:]}'}
            )
            
            # البحث عن محادثة نشطة أو إنشاء واحدة جديدة
            # المحادثة تعتبر نشطة إذا كانت خلال آخر 30 دقيقة
            thirty_mins_ago = timezone.now() - timezone.timedelta(minutes=30)
            conversation = Conversation.objects.filter(
                user=user,
                ended_at__isnull=True,
                started_at__gte=thirty_mins_ago
            ).order_by('-started_at').first()
            
            if not conversation:
                conversation = Conversation.objects.create(user=user)
            
            # إضافة الرسالة
            conversation.add_message(role, content)
            
        except Exception as e:
            logger.error(f"Error saving message: {e}")
    
    def _execute_tool(self, tool_name: str, arguments: Dict) -> str:
        """تنفيذ الأداة المطلوبة"""
        try:
            if tool_name == "search_suppliers":
                results = search_suppliers(
                    category_name=arguments.get("category_name"),
                    keywords=arguments.get("keywords"),
                    is_partner=arguments.get("is_partner")
                )
                if results:
                    return format_search_results({'database_results': results, 'google_results': [], 'total': len(results)})
                return "لم أجد نتائج في قاعدة البيانات."
            
            elif tool_name == "search_google_places":
                query = arguments.get("query", "")
                results = search_google_places(
                    query=query,
                    place_type=arguments.get("place_type"),
                    limit=5
                )
                if results:
                    return format_google_results(results, query)
                return f"لم أجد نتائج لـ '{query}' في Google Maps."
            
            elif tool_name == "combined_search":
                results = combined_search(
                    query=arguments.get("query", ""),
                    category=arguments.get("category"),
                    keywords=arguments.get("keywords")
                )
                return format_search_results(results, arguments.get("query", ""))
            
            elif tool_name == "get_categories":
                categories = get_categories()
                if categories:
                    cat_list = "\n".join([f"- {c['name_ar']}" for c in categories])
                    return f"التصنيفات المتاحة:\n{cat_list}"
                return "لا توجد تصنيفات متاحة حاليا"
            
            else:
                return f"أداة غير معروفة: {tool_name}"
        
        except Exception as e:
            logger.error(f"Tool execution error: {e}")
            return f"حدث خطأ أثناء البحث."
    
    def _process_with_intent(self, user_message: str) -> Optional[str]:
        """معالجة الرسالة باستخدام نظام النوايا الذكي"""
        intent = detect_intent(user_message)
        category = intent.entities.get('category')
        query = get_search_query(intent)
        
        # الردود المباشرة (بدون بحث)
        if intent.type in [IntentType.GREETING, IntentType.HELP, 
                           IntentType.FEEDBACK, IntentType.COMPLAINT,
                           IntentType.HUNGRY]:
            return get_intent_response_template(intent)
        
        # البحث عن خدمة (كهربائي، سباك، نجار) - قاعدة البيانات أولاً
        if intent.type == IntentType.SEARCH_SERVICE:
            results = combined_search(
                query=query,
                category=category,
                keywords=intent.entities.get('keywords', [])
            )
            if results['total'] > 0:
                # إضافة رسالة توضيحية باللهجة القصيمية
                if intent.entities.get('is_problem'):
                    intro = f"فهمت! تبي {category} 🔧\n\n"
                    return intro + format_search_results(results, category)
                return format_search_results(results, query)
        
        # البحث عن طعام/مطعم/أماكن - الموردين أولاً ثم Google (خيارين فقط)
        from .intents import GOOGLE_CATEGORIES
        if intent.type == IntentType.SEARCH_FOOD or (category and category in GOOGLE_CATEGORIES):
            search_term = category or query
            
            # البحث في الموردين أولاً
            db_results = search_suppliers(category_name=search_term, keywords=[search_term], limit=2)
            
            if db_results:
                # وجدنا في الموردين
                response = f"🔍 هذي أحسن خيارات لـ {search_term}:\n\n"
                for i, r in enumerate(db_results[:2], 1):
                    response += f"{i}. *{r['name']}*\n"
                    response += f"   ⭐ {r['rating']}/5\n"
                    if r.get('phone'):
                        response += f"   📞 {r['phone']}\n"
                    response += "\n"
                response += "تبي شي ثاني؟ 🐺"
                return response
            
            # لم نجد في الموردين، نبحث في Google
            google_results = search_google_places(query=search_term, limit=2)
            if google_results:
                response = f"🔍 هذي أحسن خيارات لـ {search_term}:\n\n"
                for i, r in enumerate(google_results[:2], 1):
                    response += f"{i}. *{r['name']}*\n"
                    response += f"   ⭐ {r['rating']}/5 ({r.get('total_ratings', 0)} تقييم)\n"
                    response += f"   📍 {r['address']}\n"
                    if r.get('is_open'):
                        response += f"   🕐 مفتوح ✅\n"
                    response += "\n"
                response += "تبي شي ثاني؟ 🐺"
                return response
            
            # لم نجد أي نتائج
            return f"ما لقيت {search_term} في عنيزة 😕\nجرب شي ثاني!"
        
        # البحث عن مكان - Google Maps
        if intent.type == IntentType.SEARCH_PLACE and intent.use_google:
            results = search_google_places(query=query, limit=5)
            if results:
                return format_google_results(results, query)
        
        # طلب الأفضل - Google Maps
        if intent.type == IntentType.GET_BEST:
            results = search_google_places(query=query, limit=5)
            if results:
                return format_google_results(results, query)
        
        # إذا وجدنا تصنيف لكن لم نعالجه، نبحث
        if category:
            if intent.use_google:
                results = search_google_places(query=category, limit=5)
                if results:
                    return format_google_results(results, category)
            else:
                results = combined_search(query=category, category=category)
                if results['total'] > 0:
                    return format_search_results(results, category)
        
        return None
    
    def _smart_search(self, query: str, category: str = None, use_google: bool = False) -> str:
        """
        بحث ذكي: الموردين أولاً، ثم Google إذا لم نجد
        """
        from .intents import GOOGLE_CATEGORIES, DATABASE_CATEGORIES
        
        search_term = category or query
        
        # تحديد مصدر البحث الأولي
        search_db_first = category in DATABASE_CATEGORIES if category else not use_google
        
        if search_db_first:
            # البحث في الموردين أولاً
            db_results = search_suppliers(category_name=search_term, keywords=[search_term], limit=2)
            if db_results:
                response = f"🔍 هذي أحسن الخيارات لـ {search_term}:\n\n"
                for i, r in enumerate(db_results[:2], 1):
                    response += f"{i}. *{r['name']}*\n"
                    response += f"   ⭐ {r['rating']}/5\n"
                    if r.get('phone'):
                        response += f"   📞 {r['phone']}\n"
                    response += "\n"
                response += "تبي شي ثاني؟ 🐺"
                return response
            
            # لم نجد في الموردين، نبحث في Google
            logger.info(f"No suppliers found for '{search_term}', searching Google...")
        
        # البحث في Google Maps
        google_results = search_google_places(query=search_term, limit=2)
        if google_results:
            response = f"🔍 هذي أحسن الخيارات لـ {search_term}:\n\n"
            for i, r in enumerate(google_results[:2], 1):
                response += f"{i}. *{r['name']}*\n"
                response += f"   ⭐ {r['rating']}/5 ({r.get('total_ratings', 0)} تقييم)\n"
                response += f"   📍 {r['address']}\n"
                if r.get('is_open'):
                    response += f"   🕐 مفتوح ✅\n"
                response += "\n"
            response += "تبي شي ثاني؟ 🐺"
            return response
        
        return f"ما لقيت {search_term} في عنيزة 😕\nجرب شي ثاني!"
    
    def process_message(self, user_message: str, user_id: str = None) -> str:
        """
        معالجة رسالة المستخدم باستخدام OpenAI
        مع fallback لنظام النوايا المحلي
        """
        # حفظ رسالة المستخدم
        self._save_message(user_id, 'user', user_message)
        
        # تحليل النية
        intent = detect_intent(user_message)
        category = intent.entities.get('category')
        
        # إذا لم يكن OpenAI متاحاً، نستخدم نظام النوايا المحلي
        if not self.client:
            response = self._process_with_intent(user_message) or "ما فهمت عليك 🤔 وضح أكثر!"
            self._save_message(user_id, 'bot', response)
            return response
        
        try:
            # إضافة سياق البحث للرسالة
            context = ""
            if category:
                # البحث الذكي: موردين أولاً ثم Google
                search_result = self._smart_search(
                    query=user_message,
                    category=category,
                    use_google=intent.use_google
                )
                context = f"\n\n[نتائج البحث التلقائي]:\n{search_result}"
            
            # بناء الرسائل مع الذاكرة (آخر 5 رسائل)
            messages = [
                {"role": "system", "content": DHIBAN_SYSTEM_PROMPT}
            ]
            
            # إضافة تاريخ المحادثة
            conversation_history = self._get_conversation_history(user_id)
            if conversation_history:
                # إضافة الرسائل السابقة (بدون الرسالة الحالية لأنها ستُضاف)
                messages.extend(conversation_history[:-1] if len(conversation_history) > 1 else [])
            
            # إضافة الرسالة الحالية مع السياق
            messages.append({"role": "user", "content": user_message + context})
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.7,
                max_tokens=400
            )
            
            assistant_message = response.choices[0].message
            
            # إذا طلب الـ AI استخدام أداة
            if assistant_message.tool_calls:
                tool_results = []
                for tool_call in assistant_message.tool_calls:
                    tool_name = tool_call.function.name
                    arguments = json.loads(tool_call.function.arguments)
                    
                    logger.info(f"Executing tool: {tool_name} with args: {arguments}")
                    result = self._execute_tool(tool_name, arguments)
                    
                    # إذا لم نجد نتائج في الموردين، نبحث في Google
                    if tool_name == "search_suppliers" and "لم أجد" in result:
                        query = arguments.get("category_name") or " ".join(arguments.get("keywords", []))
                        google_result = search_google_places(query=query, limit=2)
                        if google_result:
                            result = format_google_results(google_result, query)
                    
                    tool_results.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "content": result
                    })
                
                messages.append(assistant_message)
                messages.extend(tool_results)
                
                final_response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=400
                )
                
                bot_response = final_response.choices[0].message.content
                # حفظ رد الوكيل
                self._save_message(user_id, 'bot', bot_response)
                return bot_response
            
            bot_response = assistant_message.content or "ما فهمت عليك 🤔 وضح أكثر!"
            # حفظ رد الوكيل
            self._save_message(user_id, 'bot', bot_response)
            return bot_response
        
        except Exception as e:
            logger.error(f"Agent error: {e}")
            # Fallback لنظام النوايا المحلي
            local_response = self._process_with_intent(user_message)
            if local_response:
                self._save_message(user_id, 'bot', local_response)
                return local_response
            fallback_response = "ما فهمت عليك 🤔 وضح أكثر!"
            self._save_message(user_id, 'bot', fallback_response)
            return fallback_response
    
    def get_greeting(self) -> str:
        """رسالة الترحيب باللهجة القصيمية"""
        return """هلا والله! 🐺
أنا ذيبان، دليلك في عنيزة.

وش تبي؟
🔧 كهربائي، سباك، نجار
🍽️ مطاعم، كافيهات
🏥 صيدليات، مستشفيات

قل لي وابشر!"""


# إنشاء instance واحد للوكيل
dhiban_agent = DhibanAgent()


def process_user_message(message: str, user_id: str = None) -> str:
    """دالة مساعدة لمعالجة رسائل المستخدمين"""
    return dhiban_agent.process_message(message, user_id)
