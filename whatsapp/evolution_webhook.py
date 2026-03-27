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

from users.models import WhatsAppUser
from conversations.models import Conversation
from .evolution_api import evolution_api

logger = logging.getLogger(__name__)


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

        # تجاهل الرسائل غير النصية (صور، صوت، فيديو)
        if not text:
            logger.debug(f"Non-text message from {phone_number}, skipping")
            return None

        return {
            'event': 'message',
            'phone_number': phone_number,
            'text': text,
            'contact_name': push_name,
            'message_id': key.get('id', ''),
            'instance': instance,
        }

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
    - يحفظ رسالة المستخدم في المحادثة
    - يمرر تاريخ المحادثة للوكيل (ذاكرة)
    - يحفظ رد الوكيل في نفس المحادثة
    """
    phone_number = msg.get('phone_number')
    text = msg.get('text', '').strip()
    contact_name = msg.get('contact_name', '')

    if not phone_number or not text:
        return

    logger.info(f"Processing message from {phone_number}: {text[:50]}")

    user = get_or_create_user(phone_number, contact_name)
    conversation = get_or_create_conversation(user)

    # حفظ رسالة المستخدم في المحادثة
    conversation.add_message('user', text)

    # بناء تاريخ المحادثة للذاكرة (بدون الرسالة الحالية لتجنب التكرار)
    history = build_chat_history(conversation)
    # إزالة آخر رسالة (التي أضفناها للتو) من الـ history الممرر للوكيل
    if history and history[-1].get('role') == 'user':
        history = history[:-1]

    try:
        from ai_agent.agent import dhiban_agent
        # process_message_with_history يضمن: ذاكرة كاملة + جميع Tools
        response = dhiban_agent.process_message_with_history(text, chat_history=history)

        conversation.intent_detected = 'search'
        conversation.save(update_fields=['intent_detected'])

    except Exception as e:
        logger.error(f"AI Agent error for {phone_number}: {e}", exc_info=True)
        response = "عذراً حدث خطأ. جرب مرة ثانية 🐺"

    if response:
        result = evolution_api.send_text(phone_number, response)
        if result.get('success'):
            logger.info(f"Reply sent to {phone_number}")
        else:
            logger.error(f"Failed to send reply to {phone_number}: {result.get('error')}")
        # حفظ رد الوكيل دائماً حتى لو فشل الإرسال (للسجل)
        conversation.add_message('bot', response)


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
