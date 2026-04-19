"""
Evolution API v2 Webhook Handler
يستقبل الرسائل الواردة من Evolution API ويعالجها بالوكيل الذكي مع جميع الأدوات
يدعم: atendai/evolution-api:latest
"""
import json
import logging
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.conf import settings

from users.models import WhatsAppUser
from conversations.models import Conversation
from .evolution_api import evolution_api

logger = logging.getLogger(__name__)

# كلمات تُعتبر موافقةً صريحة على الشروط (في حال ضغط المستخدم الزر أو كتب يدوياً)
CONSENT_WORDS = {
    'موافق', 'موافقة', 'اوافق', 'أوافق', 'موافقه',
    'نعم', 'أكيد', 'اكيد', 'ok', 'okay', 'yes', 'y',
    'قبول', 'أقبل', 'اقبل', 'ابدا', 'ابدأ', 'تمام',
}


def _is_consent_text(text: str) -> bool:
    """يكشف إن كان نص الرسالة يعبّر عن الموافقة على الشروط."""
    if not text:
        return False
    import re as _re
    # تطبيع: إزالة التشكيل والمسافات الزائدة والأحرف غير الحرفية حول الكلمة
    norm = _re.sub(r'[\u064B-\u0652]', '', text).strip().lower()
    norm = _re.sub(r'[^\w\u0600-\u06FF\s]', '', norm).strip()
    return norm in CONSENT_WORDS


def _send_welcome_with_consent(phone_number: str, contact_name: str = ''):
    """
    يرسل رسالة ترحيب مع:
      • زر يفتح صفحة الشروط والأحكام
      • زر "موافق" يسمح بمتابعة المحادثة
    Fallback: لو الخادم ما يدعم الأزرار → يرسل نصاً مع الرابط.
    """
    terms_url = getattr(settings, 'TERMS_URL', 'https://dhiban.com/#terms')
    greet_name = (contact_name or '').strip().split()[0] if contact_name else ''
    greeting = f"هلا والله{' يا ' + greet_name if greet_name else ''} 🐺"
    body = (
        f"{greeting}\n\n"
        "أنا *ذيبان* — دليلك الذكي في عنيزة. أقدر أساعدك تلقى أي مطعم، كافيه، "
        "صيدلية، ورشة، خدمة منزلية... كل اللي تبي 👌\n\n"
        "قبل ما نبدأ، الرجاء الاطلاع على *الشروط والأحكام* والموافقة عليها "
        "لتفعيل الخدمة. بالضغط على زر \"موافق\" فإنك تؤكّد أنك قرأت الشروط "
        "وتوافق عليها."
    )
    footer = "ذيبان · دليلك الذكي في عنيزة"
    buttons = [
        {'type': 'url', 'displayText': '📄 اقرأ الشروط', 'url': terms_url},
        {'type': 'reply', 'displayText': '✅ موافق', 'id': 'terms_accept'},
    ]
    try:
        result = evolution_api.send_buttons(
            phone=phone_number,
            body=body,
            buttons=buttons,
            footer=footer,
        )
        if result.get('success'):
            logger.info(f"[CONSENT] Welcome+consent sent to {phone_number}")
        else:
            logger.error(f"[CONSENT] Welcome send failed: {result.get('error')}")
    except Exception as e:
        logger.error(f"[CONSENT] Welcome send exception: {e}", exc_info=True)


def _mark_user_accepted_terms(user: WhatsAppUser):
    """يسجّل موافقة المستخدم على الشروط مع الطابع الزمني."""
    if user.terms_accepted:
        return
    user.terms_accepted = True
    user.terms_accepted_at = timezone.now()
    user.save(update_fields=['terms_accepted', 'terms_accepted_at'])
    logger.info(f"[CONSENT] User {user.phone_number} accepted terms at {user.terms_accepted_at}")


def _extract_text_from_message(message: dict) -> str:
    """استخراج النص من جميع أنواع رسائل Evolution API"""
    return (
        message.get('conversation')
        or message.get('extendedTextMessage', {}).get('text', '')
        or message.get('buttonsResponseMessage', {}).get('selectedDisplayText', '')
        or message.get('listResponseMessage', {}).get('title', '')
        or message.get('templateButtonReplyMessage', {}).get('selectedDisplayText', '')
        or message.get('interactiveResponseMessage', {}).get('nativeFlowResponseMessage', {}).get('paramsJson', '')
        or ''
    )


def _detect_media_type(message: dict) -> dict:
    """
    اكتشاف نوع الوسائط في الرسالة (صورة، صوت، فيديو).
    يعيد dict مع media_type و mime_type و caption أو None.
    
    Evolution API ترسل الوسائط بأشكال مختلفة:
    - إذا كان webhook base64=true: يكون base64 موجود في الـ message مباشرة
    - بعض الإصدارات ترسل base64 في حقل منفصل خارج messageObj
    """
    # صورة
    if 'imageMessage' in message:
        img = message['imageMessage']
        media_info = {
            'media_type': 'image',
            'mime_type': img.get('mimetype', 'image/jpeg'),
            'caption': img.get('caption', ''),
            'url': img.get('url', ''),
            'base64': img.get('base64', ''),
        }
        logger.info(f"[EVOLUTION] Detected image: mime={media_info['mime_type']}, has_base64={bool(media_info['base64'])}, has_url={bool(media_info['url'])}")
        return media_info
    
    # صوت / رسالة صوتية
    if 'audioMessage' in message:
        aud = message['audioMessage']
        media_info = {
            'media_type': 'audio',
            'mime_type': aud.get('mimetype', 'audio/ogg; codecs=opus'),
            'url': aud.get('url', ''),
            'base64': aud.get('base64', ''),
            'ptt': aud.get('ptt', True),
        }
        logger.info(f"[EVOLUTION] Detected audio: mime={media_info['mime_type']}, has_base64={bool(media_info['base64'])}, has_url={bool(media_info['url'])}")
        return media_info
    
    # فيديو
    if 'videoMessage' in message:
        return {
            'media_type': 'video',
            'mime_type': message['videoMessage'].get('mimetype', 'video/mp4'),
        }
    
    # مستند
    if 'documentMessage' in message:
        return {
            'media_type': 'document',
            'mime_type': message['documentMessage'].get('mimetype', ''),
        }
    
    return None


def extract_evolution_message(data: dict) -> dict:
    """
    استخراج بيانات الرسالة من payload الخاص بـ Evolution API latest.
    يدعم صيغتين للـ event name:
      - الجديد: { event: "messages.upsert", data: { key: {...}, message: {...} } }
      - القديم: { event: "MESSAGES_UPSERT", data: [{ key: {...}, message: {...} }] }
    """
    try:
        event = data.get('event', '')
        instance = data.get('instance', '')

        # أحداث غير رسائل
        if event in ('QRCODE_UPDATED', 'qrcode.updated'):
            qr = data.get('data', {}).get('qrcode', {}).get('base64', '')
            return {'event': 'qrcode', 'qrcode': qr}

        if event in ('CONNECTION_UPDATE', 'connection.update'):
            state = data.get('data', {}).get('state', '')
            return {'event': 'connection', 'state': state, 'instance': instance}

        # تجاهل أي حدث غير رسائل
        if event not in ('messages.upsert', 'MESSAGES_UPSERT', 'message'):
            logger.debug(f"Ignoring event: {event}")
            return None

        raw = data.get('data', {})

        # صيغة قائمة (بعض الإصدارات ترسل مصفوفة)
        if isinstance(raw, list):
            raw = raw[0] if raw else {}

        key = raw.get('key', {})
        from_me = key.get('fromMe', False)

        if from_me:
            return None

        remote_jid = key.get('remoteJid', '')

        # تجاهل رسائل المجموعات
        if '@g.us' in remote_jid:
            return None

        phone_number = remote_jid.replace('@s.whatsapp.net', '').strip()
        if not phone_number:
            return None

        message_obj = raw.get('message', {})
        push_name = raw.get('pushName', '') or raw.get('notifyName', '')
        text = _extract_text_from_message(message_obj)
        message_id = key.get('id', '')

        # اكتشاف الوسائط (صور، صوت)
        media_info = _detect_media_type(message_obj)

        if media_info:
            # حفظ remote_jid لاستخدامه في تحميل الوسائط
            media_info['remote_jid'] = remote_jid
            
            # فحص base64 في عدة أماكن محتملة
            if not media_info.get('base64'):
                # 1. في مستوى raw data
                raw_base64 = raw.get('base64', '')
                if raw_base64:
                    media_info['base64'] = raw_base64
                    logger.info(f"[EVOLUTION] Found base64 in raw data level")
            
            if not media_info.get('base64'):
                # 2. في مستوى data الأعلى
                top_base64 = data.get('base64', '')
                if top_base64:
                    media_info['base64'] = top_base64
                    logger.info(f"[EVOLUTION] Found base64 in top data level")
            
            # تسجيل مفصل للتشخيص
            logger.info(f"[EVOLUTION] Media detected: type={media_info['media_type']}, "
                       f"has_base64={bool(media_info.get('base64'))}, "
                       f"has_url={bool(media_info.get('url'))}, "
                       f"message_id={message_id}, "
                       f"remote_jid={remote_jid}")
            
            # تسجيل مفاتيح الـ payload للتشخيص
            logger.info(f"[EVOLUTION] Raw keys: {list(raw.keys())}")
            logger.info(f"[EVOLUTION] Message keys: {list(message_obj.keys())}")

        # رسالة وسائط (صورة أو صوت) — الأولوية للوسائط حتى لو يوجد caption نصي
        if media_info:
            logger.info(f"[EVOLUTION] Media message from {phone_number}: type={media_info['media_type']}, has_base64={bool(media_info.get('base64'))}")
            return {
                'event': 'message',
                'phone_number': phone_number,
                'text': media_info.get('caption', ''),
                'contact_name': push_name,
                'message_id': message_id,
                'instance': instance,
                'media': media_info,
            }

        # رسالة نصية عادية
        if text:
            return {
                'event': 'message',
                'phone_number': phone_number,
                'text': text,
                'contact_name': push_name,
                'message_id': message_id,
                'instance': instance,
                'media': None,
            }

        # رسالة غير مدعومة
        logger.debug(f"Unsupported message type from {phone_number}, keys={list(message_obj.keys())}")
        return None

    except Exception as e:
        logger.error(f"Evolution webhook extract error: {e}", exc_info=True)
        return None


def get_or_create_user(phone_number: str, name: str = '') -> WhatsAppUser:
    user, created = WhatsAppUser.objects.get_or_create(
        phone_number=phone_number,
        defaults={'whatsapp_id': phone_number, 'name': name},
    )
    if not created:
        user.update_last_interaction()
        if name and not user.name:
            user.name = name
            user.save(update_fields=['name'])
    return user


def get_or_create_conversation(user: WhatsAppUser) -> Conversation:
    """
    جلب محادثة نشطة خلال آخر 24 ساعة أو إنشاء محادثة جديدة.
    نافذة 24 ساعة تضمن استمرارية الذاكرة خلال اليوم.
    """
    recent = Conversation.objects.filter(
        user=user,
        ended_at__isnull=True,
        started_at__gte=timezone.now() - timezone.timedelta(hours=24),
    ).order_by('-started_at').first()
    if recent:
        return recent
    return Conversation.objects.create(user=user)


def build_chat_history(conversation: Conversation) -> list:
    """
    بناء تاريخ المحادثة بصيغة OpenAI من آخر 10 رسائل.
    """
    if not conversation.messages:
        return []
    recent = conversation.messages[-10:]
    history = []
    for msg in recent:
        role = 'user' if msg.get('role') == 'user' else 'assistant'
        content = msg.get('content', '')
        if content:
            history.append({'role': role, 'content': content})
    return history


def process_evolution_message(msg: dict):
    """
    معالجة رسالة واردة وإرسال الرد عبر الوكيل.
    يدعم: نصوص، صور، رسائل صوتية
    """
    phone_number = msg.get('phone_number')
    text = msg.get('text', '').strip()
    contact_name = msg.get('contact_name', '')
    media = msg.get('media')
    message_id = msg.get('message_id', '')

    if not phone_number:
        return

    # يجب أن يكون هناك نص أو وسائط
    if not text and not media:
        return

    logger.info(f"Processing message from {phone_number}: text={text[:50] if text else '[media]'}, media={media.get('media_type') if media else 'none'}")

    user = get_or_create_user(phone_number, contact_name)
    conversation = get_or_create_conversation(user)

    # ═══ بوابة الموافقة على الشروط ═══
    # إذا لم يوافق المستخدم بعد، نحصر التفاعل في: عرض الترحيب+الشروط، وقبول الموافقة.
    # أي رسالة أخرى تُقابَل بإعادة إرسال رسالة الترحيب.
    if not user.terms_accepted:
        # هل هذه الرسالة تعبّر عن الموافقة؟ (ضغطة زر "موافق" ترد نصاً، أو كتابة يدوية)
        if text and _is_consent_text(text):
            _mark_user_accepted_terms(user)
            conversation.add_message('user', text)
            try:
                evolution_api.send_text(
                    phone_number,
                    "تمام يا الغالي، تم تفعيل الخدمة ✅\n"
                    "الحين قل لي وش تبي: مطعم، كافيه، صيدلية، ورشة... أو أي شي في عنيزة 🐺",
                )
            except Exception as e:
                logger.error(f"[CONSENT] Post-accept welcome failed: {e}")
            conversation.add_message('bot', 'تم تفعيل الخدمة بعد الموافقة على الشروط')
            return

        # أي رسالة قبل الموافقة → إرسال رسالة الترحيب+الشروط
        logger.info(f"[CONSENT] Blocking message from {phone_number} (terms not accepted yet)")
        if text:
            conversation.add_message('user', text)
        _send_welcome_with_consent(phone_number, contact_name)
        conversation.add_message('bot', '[CONSENT_PROMPT] رسالة ترحيب + طلب الموافقة على الشروط')
        return

    # بناء تاريخ المحادثة للذاكرة (فقط للمستخدمين الموافقين)
    history = build_chat_history(conversation)

    try:
        from ai_agent.agent import dhiban_agent

        # ── معالجة الصور ──
        if media and media.get('media_type') == 'image':
            logger.info(f"[EVOLUTION] Image message from {phone_number}, message_id={message_id}")
            conversation.add_message('user', media.get('caption', '') or '📸 [صورة]')

            history_clean = history

            # ثلاث طرق للحصول على الصورة بالترتيب:
            image_base64 = media.get('base64', '')  # 1. من الـ webhook مباشرة (إذا base64=true)
            image_url = media.get('url', '')
            remote_jid = media.get('remote_jid', '')

            # 2. إذا لم يوجد base64 في الـ payload، حمّله عبر Evolution API
            if not image_base64 and message_id:
                logger.info(f"[EVOLUTION] No inline base64, downloading via API for message {message_id}, jid={remote_jid}")
                image_base64 = evolution_api.download_media_base64(message_id, remote_jid=remote_jid)
                if image_base64:
                    logger.info(f"[EVOLUTION] Downloaded image base64 via API, length={len(image_base64)}")
                else:
                    logger.warning(f"[EVOLUTION] Failed to download image via API for message {message_id}")
            
            # 3. إذا يوجد URL ولا يوجد base64، حمّل من URL مباشرة
            if not image_base64 and image_url:
                logger.info(f"[EVOLUTION] Trying to download image from URL directly")
                try:
                    from ai_agent.media import download_image_as_base64
                    image_base64 = download_image_as_base64(image_url)
                    if image_base64:
                        logger.info(f"[EVOLUTION] Downloaded image from URL, length={len(image_base64)}")
                except Exception as e:
                    logger.error(f"[EVOLUTION] URL download failed: {e}")

            if image_base64:
                logger.info(f"[EVOLUTION] Processing image with base64 (length={len(image_base64)})")
                response = dhiban_agent.process_image_message(
                    user_id=phone_number,
                    image_base64=image_base64,
                    mime_type=media.get('mime_type', 'image/jpeg'),
                    caption=media.get('caption', ''),
                    chat_history=history_clean
                )
            else:
                logger.error(f"[EVOLUTION] No base64 or URL available for image from {phone_number}")
                response = "ما قدرت أحمّل الصورة 😕\nجرب ترسلها مرة ثانية!"

        # ── معالجة الصوت ──
        elif media and media.get('media_type') == 'audio':
            logger.info(f"[EVOLUTION] Audio message from {phone_number}, message_id={message_id}")
            conversation.add_message('user', '🎤 [رسالة صوتية]')

            history_clean = history

            audio_base64 = media.get('base64', '')
            audio_url = media.get('url', '')
            remote_jid = media.get('remote_jid', '')

            if not audio_base64 and message_id:
                logger.info(f"[EVOLUTION] No inline base64 audio, downloading via API")
                audio_base64 = evolution_api.download_media_base64(message_id, remote_jid=remote_jid)
            
            if not audio_base64 and audio_url:
                logger.info(f"[EVOLUTION] Trying to download audio from URL directly")
                try:
                    import httpx, base64 as b64mod
                    resp = httpx.get(audio_url, timeout=30, follow_redirects=True)
                    resp.raise_for_status()
                    audio_base64 = b64mod.b64encode(resp.content).decode('utf-8')
                except Exception as e:
                    logger.error(f"[EVOLUTION] Audio URL download failed: {e}")

            if audio_base64:
                logger.info(f"[EVOLUTION] Processing audio with base64 (length={len(audio_base64)})")
                response = dhiban_agent.process_voice_message(
                    user_id=phone_number,
                    audio_base64=audio_base64,
                    mime_type=media.get('mime_type', 'audio/ogg'),
                    chat_history=history_clean
                )
            elif audio_url:
                logger.info(f"[EVOLUTION] Processing audio with URL")
                response = dhiban_agent.process_voice_message(
                    user_id=phone_number,
                    audio_url=audio_url,
                    mime_type=media.get('mime_type', 'audio/ogg'),
                    chat_history=history_clean
                )
            else:
                logger.error(f"[EVOLUTION] No base64 or URL available for audio from {phone_number}")
                response = "ما قدرت أحمّل الرسالة الصوتية 😕\nجرب ترسلها مرة ثانية أو اكتب لي!"

        # ── فيديو ومستندات (غير مدعومة حالياً) ──
        elif media and media.get('media_type') in ('video', 'document'):
            conversation.add_message('user', f"📎 [{media['media_type']}]")
            response = "حالياً أقدر أفهم الصور والرسائل الصوتية والنصوص 🐺\nأرسل لي صورة المنتج أو اكتب لي وش تبي!"

        # ── رسالة نصية عادية ──
        elif text:
            # history بُني قبل add_message — لا تكرار للرسالة الحالية
            response = dhiban_agent.process_message_with_history(text, chat_history=history, user_id=phone_number)
            conversation.add_message('user', text)

        else:
            response = "ما فهمت رسالتك 😕 اكتب لي أو أرسل صورة!"

        conversation.intent_detected = 'search'
        conversation.save(update_fields=['intent_detected'])

    except Exception as e:
        logger.error(f"AI Agent error for {phone_number}: {e}", exc_info=True)
        response = "عذراً حدث خطأ. جرب مرة ثانية 🐺"

    if response:
        # دعم تعدد الرسائل: الوكيل قد يرجع list عند فصل "الشريك المميز"
        # في رسالة مستقلة بعد الرد الأساسي. نرسلها بفاصل صغير للقراءة الطبيعية.
        import time as _t
        messages_to_send = response if isinstance(response, list) else [response]
        for idx, msg in enumerate(messages_to_send):
            if not msg:
                continue
            if idx > 0:
                _t.sleep(0.8)  # فاصل صغير لتبدو الرسائل متتابعة طبيعياً
            result = evolution_api.send_text(phone_number, msg)
            if result.get('success'):
                logger.info(f"Reply part {idx+1}/{len(messages_to_send)} sent to {phone_number}")
            else:
                logger.error(f"Failed to send reply part to {phone_number}: {result.get('error')}")
            conversation.add_message('bot', msg)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def evolution_webhook_handler(request):
    """Webhook handler لـ Evolution API v2 (latest)"""

    if request.method == "GET":
        return HttpResponse('Evolution Webhook OK', content_type='text/plain')

    if request.method == "POST":
        try:
            body = request.body
            data = json.loads(body)
            event = data.get('event', 'unknown')
            logger.info(f"Evolution webhook: event={event}, instance={data.get('instance', '')}")

            # تسجيل تفاصيل payload الوسائط للتشخيص
            raw_data = data.get('data', {})
            if isinstance(raw_data, dict):
                msg_obj = raw_data.get('message', {})
                if any(k in msg_obj for k in ['imageMessage', 'audioMessage', 'videoMessage']):
                    logger.info(f"[EVOLUTION-RAW] Media webhook received!")
                    logger.info(f"[EVOLUTION-RAW] data keys: {list(raw_data.keys())}")
                    logger.info(f"[EVOLUTION-RAW] message keys: {list(msg_obj.keys())}")
                    if 'imageMessage' in msg_obj:
                        img_keys = list(msg_obj['imageMessage'].keys())
                        logger.info(f"[EVOLUTION-RAW] imageMessage keys: {img_keys}")
                        logger.info(f"[EVOLUTION-RAW] has base64 in imageMessage: {'base64' in img_keys}")
                    logger.info(f"[EVOLUTION-RAW] has base64 in data: {'base64' in raw_data}")
                    logger.info(f"[EVOLUTION-RAW] has base64 in top: {'base64' in data}")

            msg = extract_evolution_message(data)

            if msg is None:
                return HttpResponse('OK', status=200)

            if msg.get('event') == 'message':
                process_evolution_message(msg)
            elif msg.get('event') == 'connection':
                state = msg.get('state', '')
                logger.info(f"WhatsApp connection state: {state}")
            elif msg.get('event') == 'qrcode':
                logger.info("QR code updated via webhook")

            return HttpResponse('OK', status=200)

        except json.JSONDecodeError:
            logger.error("Evolution webhook: invalid JSON body")
            return HttpResponse('Bad Request', status=400)
        except Exception as e:
            logger.error(f"Evolution webhook unhandled error: {e}", exc_info=True)
            return HttpResponse('OK', status=200)

    return HttpResponse('Method Not Allowed', status=405)
