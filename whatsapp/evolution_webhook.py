"""
Evolution API v2 Webhook Handler
يستقبل الرسائل الواردة من Evolution API ويعالجها بالوكيل
"""
import json
import logging
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings
from django.utils import timezone

from users.models import WhatsAppUser
from conversations.models import Conversation
from .evolution_api import evolution_api

logger = logging.getLogger(__name__)


def extract_evolution_message(data: dict) -> dict:
    """استخراج بيانات الرسالة من payload الخاص بـ Evolution API v2"""
    try:
        event = data.get('event', '')
        instance = data.get('instance', '')

        if event == 'QRCODE_UPDATED':
            return {'event': 'qrcode', 'qrcode': data.get('data', {}).get('qrcode', {}).get('base64', '')}

        if event == 'CONNECTION_UPDATE':
            state = data.get('data', {}).get('state', '')
            return {'event': 'connection', 'state': state}

        if event not in ('messages.upsert', 'MESSAGES_UPSERT'):
            return None

        msg_data = data.get('data', {})

        # Evolution API v2 format
        key = msg_data.get('key', {})
        from_me = key.get('fromMe', False)

        if from_me:
            return None

        remote_jid = key.get('remoteJid', '')
        phone_number = remote_jid.replace('@s.whatsapp.net', '').replace('@g.us', '')

        if not phone_number or '@g.us' in remote_jid:
            return None

        message = msg_data.get('message', {})
        push_name = msg_data.get('pushName', '')

        text = (
            message.get('conversation')
            or message.get('extendedTextMessage', {}).get('text', '')
            or message.get('buttonsResponseMessage', {}).get('selectedDisplayText', '')
            or message.get('listResponseMessage', {}).get('title', '')
            or ''
        )

        return {
            'event': 'message',
            'phone_number': phone_number,
            'text': text,
            'contact_name': push_name,
            'message_id': key.get('id', ''),
            'instance': instance,
        }

    except Exception as e:
        logger.error(f"Evolution webhook extract error: {e}")
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
    recent = Conversation.objects.filter(
        user=user,
        ended_at__isnull=True,
        started_at__gte=timezone.now() - timezone.timedelta(hours=24),
    ).first()
    if recent:
        return recent
    return Conversation.objects.create(user=user)


def process_evolution_message(msg: dict):
    """معالجة رسالة واردة من Evolution API وإرسال الرد"""
    phone_number = msg.get('phone_number')
    text = msg.get('text', '').strip()
    contact_name = msg.get('contact_name', '')

    if not phone_number or not text:
        return

    user = get_or_create_user(phone_number, contact_name)
    conversation = get_or_create_conversation(user)
    conversation.add_message('user', text)

    # معالجة رسائل الترحيب
    greetings = ['مرحبا', 'السلام عليكم', 'هلا', 'اهلا', 'hi', 'hello', 'ابدأ', 'start', 'مرحباً']
    if any(g in text.lower() for g in greetings):
        response = (
            "هلا والله! 🐺\n"
            "أنا ذيبان، دليلك الذكي في عنيزة!\n\n"
            "قل لي وش تحتاج وأوصلك لأحسن الخيارات 👇"
        )
        evolution_api.send_text(phone_number, response)
        conversation.add_message('bot', response)
        return

    # استخدام الوكيل
    try:
        from ai_agent.agent import process_user_message
        response = process_user_message(text, phone_number)
        conversation.intent_detected = 'search'
        conversation.save(update_fields=['intent_detected'])
    except Exception as e:
        logger.error(f"AI Agent error: {e}")
        response = "عذراً حدث خطأ. جرب مرة ثانية 🐺"

    if response:
        evolution_api.send_text(phone_number, response)
        conversation.add_message('bot', response)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def evolution_webhook_handler(request):
    """Webhook handler لـ Evolution API v2"""

    if request.method == "GET":
        return HttpResponse('Evolution Webhook OK', content_type='text/plain')

    if request.method == "POST":
        try:
            data = json.loads(request.body)
            logger.info(f"Evolution webhook received: event={data.get('event', 'unknown')}")

            msg = extract_evolution_message(data)

            if msg is None:
                return HttpResponse('OK', status=200)

            if msg.get('event') == 'message':
                process_evolution_message(msg)
            elif msg.get('event') == 'connection':
                logger.info(f"Evolution connection state: {msg.get('state')}")
            elif msg.get('event') == 'qrcode':
                logger.info("Evolution QR code updated")

            return HttpResponse('OK', status=200)

        except json.JSONDecodeError:
            logger.error("Evolution webhook: invalid JSON")
            return HttpResponse('Bad Request', status=400)
        except Exception as e:
            logger.error(f"Evolution webhook error: {e}", exc_info=True)
            return HttpResponse('OK', status=200)

    return HttpResponse('Method Not Allowed', status=405)
