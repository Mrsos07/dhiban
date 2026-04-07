"""
وكيل الذكاء الاصطناعي الرئيسي
مع تكامل Google Maps ونظام النوايا
"""
import json
import logging
from typing import Optional, Dict, List
from openai import OpenAI

from .config import OPENAI_API_KEY, OPENAI_MODEL
from .prompts import DHIBAN_SYSTEM_PROMPT as DEFAULT_SYSTEM_PROMPT
from .tools import (
    search_suppliers, search_google_places, combined_search,
    get_categories, format_search_results, format_google_results,
    build_daily_plan, build_maps_url, TOOLS
)
from .media import (
    analyze_image_from_url, analyze_image_from_base64,
    transcribe_audio_from_url, transcribe_audio_from_base64,
    format_image_analysis_response
)

logger = logging.getLogger(__name__)


class DhibanAgent:
    """
    وكيل ذيبان - الدليل الذكي لعنيزة
    مع تكامل قاعدة البيانات و Google Maps ونظام النوايا
    """
    
    # عدد الرسائل المحفوظة في الذاكرة
    MEMORY_SIZE = 15
    
    def __init__(self):
        self.client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
        self.model = OPENAI_MODEL
        # تحميل الإعدادات من قاعدة البيانات
        self._settings_cache = None
        self._settings_cache_time = None
    
    def _get_settings(self):
        """جلب إعدادات الوكيل من قاعدة البيانات مع كاش لمدة 60 ثانية"""
        import time
        now = time.time()
        
        # استخدام الكاش إذا كان محدّث خلال آخر 60 ثانية
        if self._settings_cache and self._settings_cache_time and (now - self._settings_cache_time) < 60:
            return self._settings_cache
        
        try:
            from .models import AgentSettings
            settings = AgentSettings.get_active()
            if settings:
                self._settings_cache = settings
                self._settings_cache_time = now
                return settings
        except Exception as e:
            logger.warning(f"Could not load agent settings from DB: {e}")
        
        return None
    
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
            
            elif tool_name == "build_daily_plan":
                result = build_daily_plan(
                    activities=arguments.get("activities"),
                    plan_type=arguments.get("plan_type", "daily"),
                    preferences=arguments.get("preferences")
                )
                return result
            
            else:
                return f"أداة غير معروفة: {tool_name}"
        
        except Exception as e:
            logger.error(f"Tool execution error: {e}")
            return f"حدث خطأ أثناء البحث."
    
    def process_message(self, user_message: str, user_id: str = None) -> str:
        """
        معالجة رسالة المستخدم باستخدام OpenAI فقط
        يقرأ الإعدادات (system prompt, model, temperature) من قاعدة البيانات
        """
        # التحقق من وجود OpenAI
        if not self.client:
            logger.error("OpenAI client not configured")
            return "عذراً، الخدمة غير متاحة حالياً. حاول مرة ثانية."
        
        try:
            # جلب الإعدادات من قاعدة البيانات
            db_settings = self._get_settings()
            
            # استخدام إعدادات قاعدة البيانات أو القيم الافتراضية
            system_prompt = db_settings.system_prompt if db_settings else DEFAULT_SYSTEM_PROMPT
            model = db_settings.model_name if db_settings else self.model
            temperature = db_settings.temperature if db_settings else 0.9
            max_tokens = db_settings.max_tokens if db_settings else 600
            
            # جلب تاريخ المحادثة قبل حفظ الرسالة الحالية لتجنب التكرار
            conversation_history = self._get_conversation_history(user_id)
            
            # حفظ رسالة المستخدم بعد جلب التاريخ
            self._save_message(user_id, 'user', user_message)
            
            # بناء الرسائل مع الذاكرة (آخر 5 رسائل)
            messages = [
                {"role": "system", "content": system_prompt}
            ]
            
            # إضافة تاريخ المحادثة كاملاً
            if conversation_history:
                messages.extend(conversation_history)
            
            # إضافة رسالة المستخدم الحالية
            messages.append({"role": "user", "content": user_message})
            
            # إرسال لـ OpenAI مع الأدوات - النموذج يقرر متى يستخدم الأداة بناء على المحادثة
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            assistant_message = response.choices[0].message
            
            # إذا طلب الـ AI استخدام أداة
            if assistant_message.tool_calls:
                tool_call = assistant_message.tool_calls[0]
                tool_name = tool_call.function.name
                arguments = json.loads(tool_call.function.arguments)
                
                logger.info(f"[AGENT] Tool call: {tool_name} | args: {arguments}")
                result = self._execute_tool(tool_name, arguments)
                logger.info(f"[AGENT] Tool result length: {len(result)} | preview: {repr(result[:200])}")
                
                # إذا لم نجد في الموردين ابحث في Google تلقائياً
                if tool_name == "search_suppliers" and "لم أجد" in result:
                    q = arguments.get("category_name") or " ".join(arguments.get("keywords", []))
                    logger.info(f"[AGENT] No DB results, falling back to Google: {q}")
                    google_result = search_google_places(query=q, limit=3)
                    if google_result:
                        result = format_google_results(google_result, q)
                
                # إعادة إرسال نتيجة الأداة لـ OpenAI ليصيغها بأسلوبه الودي
                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": tool_call.id,
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": tool_call.function.arguments
                        }
                    }]
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result
                })
                
                # طلب من OpenAI يصيغ النتائج بأسلوبه المحادثاتي
                final_response = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                bot_response = final_response.choices[0].message.content
                logger.info(f"[AGENT] Formatted response: {repr(str(bot_response)[:300])}")
                
                if not bot_response:
                    bot_response = result  # fallback to raw result
                
                self._save_message(user_id, 'bot', bot_response)
                return bot_response
            
            # رد مباشر من OpenAI بدون أدوات (محادثة/أسئلة توضيحية)
            bot_response = assistant_message.content
            logger.info(f"[AGENT] Direct OpenAI response (no tool): {repr(str(bot_response)[:200])}")
            if not bot_response:
                bot_response = "وش تبي بالضبط؟ وضح أكثر 🐺"
            
            self._save_message(user_id, 'bot', bot_response)
            return bot_response
        
        except Exception as e:
            logger.error(f"Agent error: {e}", exc_info=True)
            error_response = "صار خطأ، جرب مرة ثانية 🐺"
            self._save_message(user_id, 'bot', error_response)
            return error_response
    
    def process_message_with_history(self, user_message: str, chat_history: List[Dict]) -> str:
        """
        معالجة رسالة مع تاريخ محادثة مُمرَّر مباشرة.
        يُستخدم من الويب والواتساب (Evolution API).
        يقرأ system_prompt/model/temperature من قاعدة البيانات.
        يدعم جميع الأدوات: search_suppliers, search_google_places, combined_search, get_categories
        """
        if not self.client:
            logger.error("OpenAI client not configured")
            return "عذراً، الخدمة غير متاحة حالياً. حاول مرة ثانية."
        
        try:
            db_settings = self._get_settings()
            system_prompt = db_settings.system_prompt if db_settings else DEFAULT_SYSTEM_PROMPT
            model = db_settings.model_name if db_settings else self.model
            temperature = float(db_settings.temperature) if db_settings else 0.9
            max_tokens = int(db_settings.max_tokens) if db_settings else 600
            
            messages = [{"role": "system", "content": system_prompt}]
            
            if chat_history:
                messages.extend(chat_history)
            
            messages.append({"role": "user", "content": user_message})
            
            # النموذج يقرر بنفسه متى يستخدم الأداة بناء على سياق المحادثة
            logger.info(f"[AGENT-WA] Processing message with auto tool_choice")
            
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            assistant_message = response.choices[0].message
            
            if assistant_message.tool_calls:
                tool_call = assistant_message.tool_calls[0]
                tool_name = tool_call.function.name
                arguments = json.loads(tool_call.function.arguments)
                
                logger.info(f"[AGENT-WA] Tool call: {tool_name} | args: {arguments}")
                result = self._execute_tool(tool_name, arguments)
                logger.info(f"[AGENT-WA] Tool result length: {len(result)} | preview: {repr(result[:200])}")
                
                if tool_name == "search_suppliers" and "لم أجد" in result:
                    q = arguments.get("category_name") or " ".join(arguments.get("keywords", []))
                    logger.info(f"[AGENT-WA] No DB results, falling back to Google: {q}")
                    google_result = search_google_places(query=q, limit=3)
                    if google_result:
                        result = format_google_results(google_result, q)
                
                # إعادة إرسال نتيجة الأداة لـ OpenAI ليصيغها بأسلوبه الودي
                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": tool_call.id,
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": tool_call.function.arguments
                        }
                    }]
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result
                })
                
                final_response = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                bot_response = final_response.choices[0].message.content
                logger.info(f"[AGENT-WA] Formatted response: {repr(str(bot_response)[:300])}")
                
                if not bot_response:
                    bot_response = result
                return bot_response
            
            bot_response = assistant_message.content
            logger.info(f"[AGENT-WA] Direct OpenAI (no tool): {repr(str(bot_response)[:200])}")
            if not bot_response:
                bot_response = "وش تبي بالضبط؟ وضح أكثر"
            return bot_response
        
        except Exception as e:
            logger.error(f"Agent error: {e}", exc_info=True)
            return "صار خطأ، جرب مرة ثانية"

    def process_image_message(
        self,
        user_id: str = None,
        image_url: str = None,
        image_base64: str = None,
        mime_type: str = "image/jpeg",
        caption: str = "",
        chat_history: List[Dict] = None
    ) -> str:
        """
        معالجة صورة من المستخدم:
        1. تحليل الصورة بـ OpenAI Vision للتعرف على المنتج
        2. البحث عن أقرب مكان يبيعه في عنيزة عبر Google Maps
        3. إرسال النتيجة مع رابط الموقع
        """
        try:
            logger.info(f"[AGENT] Processing image from user {user_id}")
            
            # حفظ رسالة المستخدم
            img_text = caption if caption else "📸 [صورة]"
            self._save_message(user_id, 'user', img_text)
            
            # تحليل الصورة
            analysis = None
            if image_url:
                analysis = analyze_image_from_url(image_url)
            elif image_base64:
                analysis = analyze_image_from_base64(image_base64, mime_type)
            
            if not analysis:
                response = "ما قدرت أحلل الصورة 😕\nجرب ترسل صورة أوضح أو اكتب لي وش تبي!"
                self._save_message(user_id, 'bot', response)
                return response
            
            # إذا ليس منتج
            if analysis.get('is_product') is False:
                desc = analysis.get('description', 'صورة')
                response = f"📸 شفت الصورة! 🐺\n{desc}\n\nإذا تبي تسألني عن منتج، أرسل لي صورته!"
                self._save_message(user_id, 'bot', response)
                return response
            
            # بناء الرد الأولي
            product_ar = analysis.get('product_name_ar', 'منتج')
            category = analysis.get('category', '')
            description = analysis.get('description', '')
            search_query = analysis.get('search_query', '')
            place_type = analysis.get('google_place_type', '')
            
            response = f"📸 تعرفت على الصورة! 🐺\n\n"
            response += f"📦 *{product_ar}*\n"
            if description:
                response += f"📝 {description}\n"
            
            # البحث عن أقرب مكان يبيع المنتج
            if search_query or category:
                query = search_query or f"{category} في عنيزة"
                logger.info(f"[AGENT] Searching for product store: {query}")
                
                places = search_google_places(
                    query=query,
                    place_type=place_type if place_type else None,
                    limit=3,
                    save_results=True
                )
                
                if places:
                    response += f"\n🏪 أقرب مكان تلقاه فيه في عنيزة:\n\n"
                    for i, place in enumerate(places[:2], 1):
                        name = place.get('name', '')
                        rating = place.get('rating', 0)
                        address = place.get('address', '')
                        maps_url = build_maps_url(place)
                        
                        response += f"*{i}. {name}*\n"
                        if rating:
                            response += f"   ⭐ {rating}/5\n"
                        if address:
                            response += f"   📍 {address}\n"
                        if maps_url:
                            response += f"   🗺️ {maps_url}\n"
                        response += "\n"
                else:
                    response += f"\n🏪 تلقاه في: *{category}*\n"
                    response += "ما لقيت مكان محدد في Google Maps، جرب تبحث عنه يدوياً 😊\n"
            
            response += "تبي شي ثاني؟ 🐺"
            
            self._save_message(user_id, 'bot', response)
            return response
            
        except Exception as e:
            logger.error(f"[AGENT] Image processing error: {e}", exc_info=True)
            error_response = "صار خطأ في تحليل الصورة 😕 جرب مرة ثانية!"
            self._save_message(user_id, 'bot', error_response)
            return error_response
    
    def process_voice_message(
        self,
        user_id: str = None,
        audio_url: str = None,
        audio_base64: str = None,
        mime_type: str = "audio/ogg",
        download_headers: dict = None,
        chat_history: List[Dict] = None
    ) -> str:
        """
        معالجة رسالة صوتية:
        1. تحويل الصوت لنص بـ Whisper
        2. معالجة النص كرسالة عادية
        """
        try:
            logger.info(f"[AGENT] Processing voice message from user {user_id}")
            
            # تحويل الصوت لنص
            text = None
            if audio_url:
                text = transcribe_audio_from_url(audio_url, headers=download_headers)
            elif audio_base64:
                text = transcribe_audio_from_base64(audio_base64, mime_type)
            
            if not text:
                response = "ما قدرت أفهم الرسالة الصوتية 😕\nجرب ترسل صوت أوضح أو اكتب لي!"
                self._save_message(user_id, 'bot', response)
                return response
            
            logger.info(f"[AGENT] Voice transcription: {text[:100]}")
            
            # معالجة النص كرسالة عادية
            if chat_history is not None:
                return self.process_message_with_history(text, chat_history)
            else:
                return self.process_message(text, user_id)
            
        except Exception as e:
            logger.error(f"[AGENT] Voice processing error: {e}", exc_info=True)
            error_response = "صار خطأ في تحليل الصوت 😕 جرب مرة ثانية!"
            self._save_message(user_id, 'bot', error_response)
            return error_response
    
    def get_greeting(self) -> str:
        """رسالة الترحيب - تُقرأ من إعدادات قاعدة البيانات"""
        db_settings = self._get_settings()
        if db_settings and db_settings.welcome_message:
            return db_settings.welcome_message
        
        return """هلا والله! 🐺
أنا ذيبان، دليلك الشخصي في عنيزة.

وش تبي؟
�️ خطط يومية واقتراحات طلعات
🍽️ مطاعم، كافيهات، حلويات
🔧 كهربائي، سباك، نجار
🏥 صيدليات، مستشفيات

قل "وش اسوي اليوم" وابشر بخطة كاملة! 📋"""


# إنشاء instance واحد للوكيل
dhiban_agent = DhibanAgent()


def process_user_message(message: str, user_id: str = None) -> str:
    """دالة مساعدة لمعالجة رسائل المستخدمين"""
    return dhiban_agent.process_message(message, user_id)
