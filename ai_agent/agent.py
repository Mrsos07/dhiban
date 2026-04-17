"""
وكيل الذكاء الاصطناعي الرئيسي
مع تكامل Google Maps ونظام النوايا
"""
import json
import logging
from typing import Optional, Dict, List
from openai import OpenAI

from .config import OPENAI_API_KEY, OPENAI_MODEL
from .prompts import DHIBAN_SYSTEM_PROMPT as DEFAULT_SYSTEM_PROMPT, CORE_RULES
from .promotions import maybe_promote
from . import search_context as sctx
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
    
    def _format_partner_block(self, partner: Dict) -> str:
        """
        تنسيق الشريك كـ "ترشيحنا المميز" يوضع كبند أول في نتائج البحث.
        يتضمن badge واضح ليعرف المستخدم أنه شريك معتمد.
        """
        lines = [f"⭐ *ترشيحنا المميز — شريك معتمد*"]
        lines.append(f"*{partner.get('name', '')}*")
        if partner.get('rating'):
            lines.append(f"   ⭐ {partner['rating']}/5" + (f" ({partner.get('total_ratings', 0)} تقييم)" if partner.get('total_ratings') else ''))
        if partner.get('agent_notes'):
            lines.append(f"   📝 {partner['agent_notes']}")
        if partner.get('address'):
            lines.append(f"   📍 {partner['address']}")
        if partner.get('phone'):
            lines.append(f"   📞 {partner['phone']}")
        if partner.get('maps_url'):
            lines.append(f"   🗺️ الموقع:\n{partner['maps_url']}")
        return "\n".join(lines)

    def _extract_names_from_result(self, result_text: str) -> List[str]:
        """استخراج أسماء الأماكن من نص نتيجة الأداة (لتسجيل ما عُرض)."""
        import re
        if not result_text:
            return []
        # الأسماء بصيغة *اسم* على سطر منفصل (بعد الرقم أو في البداية)
        pattern = r'\*([^*\n]{2,80})\*'
        names = re.findall(pattern, result_text)
        # فلترة كلمات غير اسم مكان
        noise = {'ترشيحنا المميز', 'شريك معتمد', 'خطتك اليومية في عنيزة', 'ملاحظة'}
        return [n.strip() for n in names if n.strip() and n.strip() not in noise]

    def _execute_tool(
        self,
        tool_name: str,
        arguments: Dict,
        user_id: Optional[str] = None,
        user_message: str = '',
    ) -> str:
        """
        تنفيذ الأداة المطلوبة — مع:
          • دعم "اقترح بدائل": استبعاد الأسماء التي عُرضت سابقاً
          • حقن شريك واحد معتمد (لو متوفر للفئة) في بداية النتائج
          • تسجيل الأسماء المعروضة في سياق المستخدم
        """
        try:
            # كشف طلب البدائل + جلب الاستبعادات
            is_alt = sctx.is_alternatives_request(user_message)
            exclusions = sctx.get_exclusions(user_id) if is_alt else set()

            def _finalize_with_partner(
                result_text: str,
                category_hint: str,
                specific_terms: Optional[List[str]] = None,
            ) -> str:
                """
                يضيف:
                  1) شريكاً معتمداً رئيسياً في رأس النتائج (لو توفر للفئة)
                     — مع مطابقة دقيقة على specific_terms (مثلاً "بروست") لتنويع ذكي.
                  2) شريكاً مرافقاً من فئة قريبة في ذيل الرد (cross-sell ذكي)
                ثم يسجّل الأسماء المعروضة.
                """
                main_partner = sctx.find_best_partner(
                    category=category_hint,
                    user_phone=user_id,
                    specific_terms=specific_terms,
                )
                main_partner_id = None
                if main_partner and main_partner.get('name') and main_partner['name'] not in (result_text or ''):
                    block = self._format_partner_block(main_partner)
                    result_text = f"{block}\n\n{result_text}"
                    main_partner_id = main_partner.get('_partner_id', '')
                    sctx.record_partner_promotion(
                        user_phone=user_id,
                        partner_id=main_partner_id,
                        category=category_hint,
                        user_message=user_message,
                    )
                    logger.info(f"[AGENT] Injected main partner '{main_partner['name']}' for '{category_hint}'")

                # 2) اقتراح شريك مرافق من فئة مكمّلة (cross-sell)
                # مثال: المستخدم طلب مطعم → نقترح سوبرماركت/كافيه شريك
                try:
                    companion = sctx.find_companion_partner(
                        current_category=category_hint,
                        user_phone=user_id,
                        exclude_partner_id=main_partner_id,
                    )
                    if companion and companion.get('partner'):
                        comp_partner = companion['partner']
                        if comp_partner.get('name') and comp_partner['name'] not in result_text:
                            comp_block = sctx.format_companion_block(companion)
                            result_text = f"{result_text}\n{comp_block}"
                            sctx.record_partner_promotion(
                                user_phone=user_id,
                                partner_id=comp_partner.get('_partner_id', ''),
                                category=companion.get('companion_category', ''),
                                user_message=f"[companion:{category_hint}] {user_message}",
                            )
                            logger.info(
                                f"[AGENT] Injected companion partner '{comp_partner['name']}' "
                                f"({companion.get('companion_category')}) after {category_hint}"
                            )
                except Exception as e:
                    logger.error(f"[AGENT] companion injection failed (non-fatal): {e}")

                # تسجيل كل الأسماء المعروضة (للاستبعاد في الطلب القادم)
                shown = self._extract_names_from_result(result_text)
                if shown:
                    sctx.record_search(user_id, category_hint, shown)
                return result_text

            # خريطة place_type إنجليزي → فئة عربية
            category_map = {
                'restaurant': 'مطعم', 'cafe': 'كافيه', 'pharmacy': 'صيدلية',
                'bakery': 'مخبز', 'supermarket': 'سوبرماركت',
                'gas_station': 'محطة وقود', 'atm': 'صراف آلي',
                'hair_salon': 'حلاق', 'barber_shop': 'حلاق',
                'beauty_salon': 'صالون تجميل', 'gym': 'صالة رياضية',
                'park': 'حديقة', 'hospital': 'مستشفى',
            }

            if tool_name == "search_suppliers":
                category_hint = arguments.get("category_name") or ''
                keywords = [k for k in (arguments.get("keywords") or []) if k]
                specific_terms = [k for k in keywords if k != category_hint]

                # البحث الشلالي: DB أولاً مع تنويع + استبعاد الأسماء المعروضة
                results = search_suppliers(
                    category_name=category_hint,
                    keywords=keywords,
                    is_partner=arguments.get("is_partner"),
                    limit=5,
                    exclude_names=exclusions if exclusions else None,
                    randomize=True,
                )
                if results:
                    formatted = format_search_results(
                        {'database_results': results, 'google_results': [], 'total': len(results)}
                    )
                    # لو الـ category فارغة، استخدم أول keyword كتلميح
                    eff_category = category_hint or (keywords[0] if keywords else '')
                    return _finalize_with_partner(formatted, eff_category, specific_terms=specific_terms)

                # DB فارغة → جرّب Google كـ fallback مع حقن شريك بنفس الفئة
                q = category_hint or ' '.join(keywords)
                logger.info(f"[AGENT] search_suppliers empty → falling back to Google: {q}")
                google_results = search_google_places(
                    query=q, limit=5,
                    exclude_names=exclusions if exclusions else None,
                )
                if google_results:
                    formatted = format_google_results(google_results, q)
                    eff_category = category_hint or (keywords[0] if keywords else '')
                    return _finalize_with_partner(formatted, eff_category, specific_terms=specific_terms)
                return "لم أجد نتائج في قاعدة البيانات ولا في Google Maps."

            elif tool_name == "search_google_places":
                query = arguments.get("query", "")
                place_type = arguments.get("place_type", "")
                # استخراج المصطلحات المحددة (نوع الأكل مثلاً) من الـ query
                category = category_map.get(place_type, place_type or query)
                specific_terms = []
                if query:
                    # كلمات ≥ 2 حروف داخل الـ query، مع تنظيف كلمات مثل "مطعم"
                    raw_tokens = [t.strip() for t in query.split() if len(t.strip()) >= 2]
                    generic = {'مطعم', 'مطاعم', 'كافيه', 'كوفي', 'محل', 'في', 'عنيزة'}
                    specific_terms = [t for t in raw_tokens if t not in generic]

                # جرّب موردي DB أولاً (شركاء + عاديين) مع الكلمات المحددة — أولوية أعلى من Google
                if specific_terms or category:
                    db_results = search_suppliers(
                        category_name=category,
                        keywords=specific_terms or None,
                        limit=5,
                        exclude_names=exclusions if exclusions else None,
                        randomize=True,
                    )
                    if db_results:
                        formatted = format_search_results(
                            {'database_results': db_results, 'google_results': [], 'total': len(db_results)}
                        )
                        return _finalize_with_partner(formatted, category, specific_terms=specific_terms)

                # DB ما فيها شي → Google
                results = search_google_places(
                    query=query,
                    place_type=place_type or None,
                    limit=5,
                    exclude_names=exclusions if exclusions else None,
                )
                if results:
                    formatted = format_google_results(results, query)
                    return _finalize_with_partner(formatted, category, specific_terms=specific_terms)
                if exclusions:
                    return f"ما لقيت خيارات جديدة غير اللي ذكرتها قبل لـ '{query}' 😕 تبي أوسّع البحث أو أغيّر الكلمات؟"
                return f"لم أجد نتائج لـ '{query}' في Google Maps."

            elif tool_name == "combined_search":
                query = arguments.get("query", "")
                category = arguments.get("category") or ''
                keywords = [k for k in (arguments.get("keywords") or []) if k]
                specific_terms = [k for k in keywords if k != category] or (
                    [query] if query and query != category else []
                )

                results = combined_search(
                    query=query,
                    category=category or None,
                    keywords=keywords or None,
                )
                if exclusions:
                    results['database_results'] = [
                        r for r in results.get('database_results', [])
                        if r.get('name', '').strip() not in exclusions
                    ]
                    results['google_results'] = [
                        r for r in results.get('google_results', [])
                        if r.get('name', '').strip() not in exclusions
                    ]
                formatted = format_search_results(results, query)
                eff_category = category or query
                return _finalize_with_partner(formatted, eff_category, specific_terms=specific_terms)

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
                # تسجيل الأسماء من الخطة لمنع التكرار في طلبات لاحقة
                shown = self._extract_names_from_result(result)
                if shown and user_id:
                    sctx.record_search(user_id, 'plan', shown)
                return result

            else:
                return f"أداة غير معروفة: {tool_name}"

        except Exception as e:
            logger.error(f"Tool execution error: {e}", exc_info=True)
            return f"حدث خطأ أثناء البحث."
    
    def _inject_promotion(self, bot_response: str, user_message: str, user_id: Optional[str]) -> str:
        """
        يحقن ترشيح شريك ذكي بعد الرد في حال لم يكن الشريك مدمجاً أصلاً في النتائج.
        الشريك الأساسي يُحقن داخل نتائج البحث عبر _execute_tool، فإذا سبق حقنه نتخطى.
        هذا الـ hook يعمل فقط للردود الحوارية البحتة (بدون tool call).
        """
        try:
            if not user_id or not bot_response:
                return bot_response
            # لو الرد أصلاً يحتوي شريكاً معتمداً (من نتائج الأداة)، لا نضيف ترويجاً ثانياً
            if 'ترشيحنا المميز' in bot_response or 'شريك معتمد' in bot_response:
                return bot_response
            promo = maybe_promote(user_id, user_message or '', bot_response)
            if promo:
                return f"{bot_response}\n\n{promo}"
        except Exception as e:
            logger.error(f"[AGENT] Promotion injection failed (non-fatal): {e}")
        return bot_response

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
            max_tokens = db_settings.max_tokens if db_settings else 800
            
            # جلب تاريخ المحادثة قبل حفظ الرسالة الحالية لتجنب التكرار
            conversation_history = self._get_conversation_history(user_id)
            
            # حفظ رسالة المستخدم بعد جلب التاريخ
            self._save_message(user_id, 'user', user_message)
            
            # بناء الرسائل مع الذاكرة (آخر 5 رسائل)
            # CORE_RULES يوضع أخيراً كي يطغى على أي تعليمات مخففة في DB prompt
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "system", "content": CORE_RULES},
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
                result = self._execute_tool(tool_name, arguments, user_id=user_id, user_message=user_message)
                logger.info(f"[AGENT] Tool result length: {len(result)} | preview: {repr(result[:200])}")
                
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
                # نضيف تعليمة صارمة: قدّم النتائج كما هي فقط ولا تخترع أي اسم مكان إضافي
                messages_with_guard = messages + [{
                    "role": "system",
                    "content": (
                        "قدّم فقط الأماكن/الأسماء التي وردت حرفياً في نتيجة الأداة أعلاه. "
                        "ممنوع منعاً باتاً إضافة أي اسم مطعم/محل/كافيه/مكان غير موجود في النتيجة. "
                        "ممنوع تخمين أرقام هواتف أو عناوين أو تقييمات. "
                        "إذا النتيجة فارغة قل بصراحة إنك ما لقيت واسأل المستخدم إذا يبي تجرب بحث ثاني."
                    )
                }]
                # temperature منخفضة في مرحلة التنسيق لتقليل الاختراع
                format_temp = min(float(temperature), 0.3)
                final_response = self.client.chat.completions.create(
                    model=model,
                    messages=messages_with_guard,
                    temperature=format_temp,
                    max_tokens=max_tokens
                )
                bot_response = final_response.choices[0].message.content
                logger.info(f"[AGENT] Formatted response: {repr(str(bot_response)[:300])}")
                
                if not bot_response:
                    bot_response = result  # fallback to raw result
                
                bot_response = self._inject_promotion(bot_response, user_message, user_id)
                self._save_message(user_id, 'bot', bot_response)
                return bot_response
            
            # رد مباشر من OpenAI بدون أدوات (محادثة/أسئلة توضيحية)
            bot_response = assistant_message.content
            logger.info(f"[AGENT] Direct OpenAI response (no tool): {repr(str(bot_response)[:200])}")
            if not bot_response:
                bot_response = "ها يالغالي؟ وضح لي شوي وش تبي بالضبط 🐺"
            
            bot_response = self._inject_promotion(bot_response, user_message, user_id)
            self._save_message(user_id, 'bot', bot_response)
            return bot_response
        
        except Exception as e:
            logger.error(f"Agent error: {e}", exc_info=True)
            error_response = "يالغالي صار خطأ بسيط، جرب مرة ثانية وابشر 🐺"
            self._save_message(user_id, 'bot', error_response)
            return error_response
    
    def process_message_with_history(self, user_message: str, chat_history: List[Dict], user_id: str = None) -> str:
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
            max_tokens = int(db_settings.max_tokens) if db_settings else 800
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "system", "content": CORE_RULES},
            ]
            
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
                result = self._execute_tool(tool_name, arguments, user_id=user_id, user_message=user_message)
                logger.info(f"[AGENT-WA] Tool result length: {len(result)} | preview: {repr(result[:200])}")
                
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
                
                messages_with_guard = messages + [{
                    "role": "system",
                    "content": (
                        "قدّم فقط الأماكن/الأسماء التي وردت حرفياً في نتيجة الأداة أعلاه. "
                        "ممنوع منعاً باتاً إضافة أي اسم مطعم/محل/كافيه/مكان غير موجود في النتيجة. "
                        "ممنوع تخمين أرقام هواتف أو عناوين أو تقييمات. "
                        "إذا النتيجة فارغة قل بصراحة إنك ما لقيت واسأل المستخدم إذا يبي تجرب بحث ثاني."
                    )
                }]
                format_temp = min(float(temperature), 0.3)
                final_response = self.client.chat.completions.create(
                    model=model,
                    messages=messages_with_guard,
                    temperature=format_temp,
                    max_tokens=max_tokens
                )
                bot_response = final_response.choices[0].message.content
                logger.info(f"[AGENT-WA] Formatted response: {repr(str(bot_response)[:300])}")
                
                if not bot_response:
                    bot_response = result
                return self._inject_promotion(bot_response, user_message, user_id)
            
            bot_response = assistant_message.content
            logger.info(f"[AGENT-WA] Direct OpenAI (no tool): {repr(str(bot_response)[:200])}")
            if not bot_response:
                bot_response = "ها يالغالي؟ خبرني وش تبي بالضبط"
            return self._inject_promotion(bot_response, user_message, user_id)
        
        except Exception as e:
            logger.error(f"Agent error: {e}", exc_info=True)
            return "يالغالي صار خطأ بسيط، جرب مرة ثانية وابشر"

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
        معالجة صورة من المستخدم — بأسلوب محادثاتي:
        1. تحليل الصورة بـ OpenAI Vision للتعرف على المنتج
        2. وصف المنتج بشكل ودي وسؤال العميل إذا يبي يبحث
        3. إذا العميل قال ابحث → يبحث في عنيزة فقط بأعلى تقييم
        
        ⚠️ لا يبحث تلقائياً — يسأل العميل أول!
        """
        try:
            logger.info(f"[AGENT] Processing image from user {user_id}, "
                       f"has_url={bool(image_url)}, has_base64={bool(image_base64)}, "
                       f"base64_len={len(image_base64) if image_base64 else 0}, "
                       f"mime={mime_type}, caption='{caption[:50] if caption else ''}'")
            
            # حفظ رسالة المستخدم
            img_text = caption if caption else "📸 [صورة]"
            self._save_message(user_id, 'user', img_text)
            
            # تحليل الصورة
            analysis = None
            if image_base64:
                logger.info(f"[AGENT] Calling analyze_image_from_base64 (len={len(image_base64)})")
                analysis = analyze_image_from_base64(image_base64, mime_type)
                logger.info(f"[AGENT] analyze_image_from_base64 returned: {type(analysis)} = {repr(analysis)[:200] if analysis else 'None'}")
            elif image_url:
                logger.info(f"[AGENT] Calling analyze_image_from_url: {image_url[:100]}")
                analysis = analyze_image_from_url(image_url)
                logger.info(f"[AGENT] analyze_image_from_url returned: {type(analysis)} = {repr(analysis)[:200] if analysis else 'None'}")
            else:
                logger.error(f"[AGENT] No image_base64 or image_url provided!")
            
            if not analysis:
                logger.error(f"[AGENT] Image analysis returned None for user {user_id}")
                response = "يالغالي ما قدرت أوضح الصورة 😕\nجرب ترسل صورة أوضح أو اكتب لي وش تبي!"
                self._save_message(user_id, 'bot', response)
                return response
            
            # ═══ إذا ليس منتج (أكل، مكان، طبيعة، شخص) ═══
            if analysis.get('is_product') is False:
                desc = analysis.get('description', 'صورة حلوة')
                image_type = analysis.get('image_type', 'other')
                
                # رد محادثاتي حسب نوع الصورة
                if image_type == 'food':
                    response = f"يا سلام! 😋 شكله لذيذ!\n{desc}\n\nتبي أدلك على مطعم يسوي زيه في عنيزة؟ 🐺"
                elif image_type == 'place':
                    response = f"📸 مكان حلو ما شاء الله!\n{desc}\n\nتبي أوريك أماكن زي كذا في عنيزة؟ 😊"
                elif image_type == 'nature':
                    response = f"📸 ما شاء الله منظر يريح النفس!\n{desc}\n\nتبي أقترح لك أماكن طبيعة حلوة في عنيزة؟ 🌿"
                else:
                    response = f"📸 شفت الصورة يالغالي!\n{desc}\n\nإذا تبي تسألني عن شي أو تبي أبحث لك، قل لي وابشر! 🐺"
                
                self._save_message(user_id, 'bot', response)
                return response
            
            # ═══ منتج → وصف + سؤال (لا نبحث مباشرة!) ═══
            product_ar = analysis.get('product_name_ar', 'منتج')
            brand = analysis.get('brand', '')
            category = analysis.get('category', '')
            description = analysis.get('description', '')
            search_query = analysis.get('search_query', '')
            place_type = analysis.get('google_place_type', '')
            price_range = analysis.get('estimated_price_range', '')
            
            # بناء رد محادثاتي يسولف عن المنتج ويسأل
            response = f"يا حلوه! عرفت الصورة �\n\n"
            
            if brand:
                response += f"📦 *{product_ar}* — {brand}\n"
            else:
                response += f"📦 *{product_ar}*\n"
            
            if description:
                response += f"{description}\n"
            
            if price_range:
                response += f"💰 السعر تقريباً: {price_range}\n"
            
            response += f"\n"
            
            # ═══ إذا المستخدم أرسل كابشن فيه طلب بحث → ابحث مباشرة ═══
            caption_lower = caption.strip().lower() if caption else ''
            search_triggers = ['ابحث', 'وين', 'ابي', 'ابغى', 'دور', 'لقني', 'بحث', 'اقرب', 'مكان']
            should_search = any(trigger in caption_lower for trigger in search_triggers)
            
            if should_search and (search_query or category):
                # المستخدم طلب بحث في الكابشن → نبحث مباشرة في عنيزة
                response += self._search_product_in_unaizah(
                    search_query, category, place_type, product_ar
                )
            else:
                # لا نبحث — نسأل العميل أول
                if category:
                    response += f"تبي أبحث لك عن *{category}* في عنيزة يبيع هالمنتج بتقييم عالي؟ 😊\n"
                else:
                    response += f"تبي أبحث لك عن مكان يبيعه في عنيزة؟ 😊\n"
                response += "قل لي *ابحث* وابشر! 🐺"
            
            self._save_message(user_id, 'bot', response)
            return response
            
        except Exception as e:
            logger.error(f"[AGENT] Image processing error: {e}", exc_info=True)
            error_response = "يالغالي صار خطأ بسيط في تحليل الصورة 😕 جرب مرة ثانية!"
            self._save_message(user_id, 'bot', error_response)
            return error_response
    
    def _search_product_in_unaizah(
        self,
        search_query: str,
        category: str,
        place_type: str,
        product_ar: str
    ) -> str:
        """البحث عن مكان يبيع المنتج في عنيزة فقط — مرتب بالتقييم الأعلى"""
        query = search_query or f"{category} في عنيزة"
        # التأكد من أن البحث مقيد بعنيزة
        if 'عنيزة' not in query:
            query += ' في عنيزة'
        
        logger.info(f"[AGENT] Searching for product in Unaizah: {query}")
        
        places = search_google_places(
            query=query,
            place_type=place_type if place_type else None,
            limit=5,
            save_results=True
        )
        
        if not places:
            return f"بحثت لك في عنيزة بس ما لقيت مكان محدد يبيع *{product_ar}* 😕\nجرب تسأل في *{category}* القريبة منك\n\nتبي شي ثاني؟ 🐺"
        
        # ترتيب حسب التقييم (الأعلى أول)
        places_sorted = sorted(places, key=lambda p: (p.get('rating', 0), p.get('total_ratings', 0)), reverse=True)
        
        result = f"لقيت لك أحسن الأماكن في *عنيزة* اللي تبيع هالمنتج:\n\n"
        
        for i, place in enumerate(places_sorted[:3], 1):
            name = place.get('name', '')
            rating = place.get('rating', 0)
            total_ratings = place.get('total_ratings', 0)
            address = place.get('address', '')
            phone = place.get('phone', '')
            is_open = place.get('is_open')
            maps_url = build_maps_url(place)
            
            if i == 1:
                result += f"⭐ *{name}* — أنصحك فيه!\n"
            else:
                result += f"*{i}. {name}*\n"
            
            if rating:
                result += f"   ⭐ {rating}/5"
                if total_ratings:
                    result += f" ({total_ratings} تقييم)"
                result += "\n"
            if address:
                result += f"   📍 {address}\n"
            if phone:
                result += f"   � {phone}\n"
            if is_open is not None:
                result += f"   🕐 {'✅ مفتوح الحين' if is_open else '❌ مغلق الحين'}\n"
            if maps_url:
                result += f"   🗺️ الموقع:\n{maps_url}\n"
            result += "\n"
        
        result += "تبي شي ثاني يالغالي؟ 🐺"
        return result
    
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
                return self.process_message_with_history(text, chat_history, user_id=user_id)
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
        
        return """هلا يالغالي! 🐺
أنا ذيبان، قصيمي أصيل وأعرف كل زاوية في عنيزة.

قل لي وش تبي وابشر:
🗺️ خطط وخروجات
🍽️ مطاعم وكافيهات
🔧 كهربائي، سباك، نجار
🏥 صيدليات ومستشفيات

سولفني وش جوك اليوم! 😊"""


# إنشاء instance واحد للوكيل
dhiban_agent = DhibanAgent()


def process_user_message(message: str, user_id: str = None) -> str:
    """دالة مساعدة لمعالجة رسائل المستخدمين"""
    return dhiban_agent.process_message(message, user_id)
