"""
وكيل الذكاء الاصطناعي الرئيسي
مع تكامل Google Maps ونظام النوايا
"""
import json
import logging
from typing import Optional, Dict, List
from openai import OpenAI

from .config import OPENAI_API_KEY, OPENAI_MODEL
from .prompts import DHIBAN_SYSTEM_PROMPT
from .tools import (
    search_suppliers, search_google_places, combined_search,
    get_categories, format_search_results, format_google_results, TOOLS
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
    
    def process_message(self, user_message: str, user_id: str = None) -> str:
        """
        معالجة رسالة المستخدم باستخدام OpenAI فقط
        بدون أي ردود جاهزة أو موك - الوكيل يرد من نفسه
        """
        # حفظ رسالة المستخدم
        self._save_message(user_id, 'user', user_message)
        
        # التحقق من وجود OpenAI
        if not self.client:
            logger.error("OpenAI client not configured")
            return "عذراً، الخدمة غير متاحة حالياً. حاول مرة ثانية."
        
        try:
            # بناء الرسائل مع الذاكرة (آخر 5 رسائل)
            messages = [
                {"role": "system", "content": DHIBAN_SYSTEM_PROMPT}
            ]
            
            # إضافة تاريخ المحادثة
            conversation_history = self._get_conversation_history(user_id)
            if conversation_history:
                messages.extend(conversation_history[:-1] if len(conversation_history) > 1 else [])
            
            # إضافة رسالة المستخدم
            messages.append({"role": "user", "content": user_message})
            
            # إرسال لـ OpenAI مع الأدوات
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.7,
                max_tokens=500
            )
            
            assistant_message = response.choices[0].message
            
            # إذا طلب الـ AI استخدام أداة
            if assistant_message.tool_calls:
                tool_results = []
                for tool_call in assistant_message.tool_calls:
                    tool_name = tool_call.function.name
                    arguments = json.loads(tool_call.function.arguments)
                    
                    logger.info(f"Tool call: {tool_name} | args: {arguments}")
                    result = self._execute_tool(tool_name, arguments)
                    
                    # إذا لم نجد نتائج في الموردين، نبحث في Google تلقائياً
                    if tool_name == "search_suppliers" and "لم أجد" in result:
                        query = arguments.get("category_name") or " ".join(arguments.get("keywords", []))
                        google_result = search_google_places(query=query, limit=3)
                        if google_result:
                            result = format_google_results(google_result, query)
                    
                    tool_results.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "content": result
                    })
                
                # إرسال نتائج الأدوات لـ OpenAI ليصيغ الرد بنفسه
                messages.append(assistant_message)
                messages.extend(tool_results)
                
                final_response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=500
                )
                
                bot_response = final_response.choices[0].message.content
                self._save_message(user_id, 'bot', bot_response)
                return bot_response
            
            # رد مباشر من OpenAI بدون أدوات
            bot_response = assistant_message.content
            if not bot_response:
                bot_response = "وش تبي بالضبط؟ وضح أكثر 🐺"
            
            self._save_message(user_id, 'bot', bot_response)
            return bot_response
        
        except Exception as e:
            logger.error(f"Agent error: {e}", exc_info=True)
            error_response = "صار خطأ، جرب مرة ثانية 🐺"
            self._save_message(user_id, 'bot', error_response)
            return error_response
    
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
