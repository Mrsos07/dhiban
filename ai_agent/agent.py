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
    get_categories, format_search_results, TOOLS
)
from .intents import detect_intent, IntentType, get_intent_response_template

logger = logging.getLogger(__name__)


class DhibanAgent:
    """
    وكيل ذيبان - الدليل الذكي لعنيزة
    مع تكامل قاعدة البيانات و Google Maps ونظام النوايا
    """
    
    def __init__(self):
        self.client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
        self.model = OPENAI_MODEL
    
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
                results = search_google_places(
                    query=arguments.get("query", ""),
                    place_type=arguments.get("place_type")
                )
                if results:
                    return format_search_results({'database_results': [], 'google_results': results, 'total': len(results)})
                return "لم أجد نتائج في Google Maps."
            
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
        """معالجة الرسالة باستخدام نظام النوايا (بدون OpenAI)"""
        intent = detect_intent(user_message)
        
        # التحية
        if intent.type == IntentType.GREETING:
            return get_intent_response_template(intent)
        
        # المساعدة
        if intent.type == IntentType.HELP:
            return get_intent_response_template(intent)
        
        # الملاحظات
        if intent.type == IntentType.FEEDBACK:
            return get_intent_response_template(intent)
        
        # الشكوى
        if intent.type == IntentType.COMPLAINT:
            return get_intent_response_template(intent)
        
        # البحث عن خدمة أو مكان
        if intent.type in [IntentType.SEARCH_SERVICE, IntentType.SEARCH_PLACE]:
            category = intent.entities.get('category')
            keywords = intent.entities.get('keywords', [])
            
            if category or keywords:
                results = combined_search(
                    query=user_message,
                    category=category,
                    keywords=keywords if keywords else [user_message]
                )
                return format_search_results(results, user_message)
        
        return None
    
    def process_message(self, user_message: str, user_id: str = None) -> str:
        """
        معالجة رسالة المستخدم وإرجاع الرد
        """
        # أولا: محاولة المعالجة بنظام النوايا المحلي
        intent_response = self._process_with_intent(user_message)
        if intent_response:
            return intent_response
        
        # ثانيا: استخدام OpenAI إذا كان متاحا
        if not self.client:
            # إذا لم يكن OpenAI متاحا نستخدم البحث المباشر
            intent = detect_intent(user_message)
            results = combined_search(
                query=user_message,
                category=intent.entities.get('category'),
                keywords=intent.entities.get('keywords')
            )
            
            if results['total'] > 0:
                return format_search_results(results, user_message)
            else:
                return "عذرا لم أجد نتائج. جرب وصفا مختلفا أو أرسل 'مساعدة' لمعرفة كيف أقدر أساعدك."
        
        try:
            messages = [
                {"role": "system", "content": DHIBAN_SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ]
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.7,
                max_tokens=1000
            )
            
            assistant_message = response.choices[0].message
            
            if assistant_message.tool_calls:
                tool_results = []
                for tool_call in assistant_message.tool_calls:
                    tool_name = tool_call.function.name
                    arguments = json.loads(tool_call.function.arguments)
                    
                    logger.info(f"Executing tool: {tool_name} with args: {arguments}")
                    result = self._execute_tool(tool_name, arguments)
                    
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
                    max_tokens=1000
                )
                
                return final_response.choices[0].message.content
            
            return assistant_message.content or "عذرا لم أفهم طلبك. هل يمكنك التوضيح"
        
        except Exception as e:
            logger.error(f"Agent error: {e}")
            # Fallback إلى البحث المباشر
            intent = detect_intent(user_message)
            results = combined_search(
                query=user_message,
                category=intent.entities.get('category')
            )
            if results['total'] > 0:
                return format_search_results(results, user_message)
            return "عذرا حدث خطأ. يرجى المحاولة مرة أخرى."
    
    def get_greeting(self) -> str:
        """رسالة الترحيب"""
        return """مرحبا! أنا ذيبان 
دليلك الذكي في عنيزة!

كيف أقدر أساعدك اليوم
- ابحث لك عن كهربائي سباك نجار...
- أدلك على أفضل المطاعم والمقاهي
- أوصلك بأي خدمة تحتاجها

فقط قل لي وش تبي! """


# إنشاء instance واحد للوكيل
dhiban_agent = DhibanAgent()


def process_user_message(message: str, user_id: str = None) -> str:
    """دالة مساعدة لمعالجة رسائل المستخدمين"""
    return dhiban_agent.process_message(message, user_id)
