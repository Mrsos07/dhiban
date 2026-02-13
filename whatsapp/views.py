"""
WhatsApp Business API Webhook
يستقبل الرسائل من واتساب ويعالجها عبر الوكيل الذكي
"""
import json
import logging
import hashlib
import hmac
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings

from ai_agent.agent import process_user_message

logger = logging.getLogger(__name__)


def verify_webhook_signature(request):
    """التحقق من توقيع الـ webhook"""
    signature = request.headers.get('X-Hub-Signature-256', '')
    if not signature or not settings.WHATSAPP_APP_SECRET:
        return True  # تخطي التحقق إذا لم يكن مُعداً
    
    expected_signature = 'sha256=' + hmac.new(
        settings.WHATSAPP_APP_SECRET.encode('utf-8'),
        request.body,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(signature, expected_signature)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def webhook(request):
    """
    WhatsApp Webhook Endpoint
    GET: للتحقق من الـ webhook
    POST: لاستقبال الرسائل
    """
    if request.method == 'GET':
        return verify_webhook(request)
    else:
        return handle_message(request)


def verify_webhook(request):
    """التحقق من الـ webhook (Challenge)"""
    mode = request.GET.get('hub.mode')
    token = request.GET.get('hub.verify_token')
    challenge = request.GET.get('hub.challenge')
    
    if mode == 'subscribe' and token == settings.WHATSAPP_VERIFY_TOKEN:
        logger.info("Webhook verified successfully")
        return HttpResponse(challenge, content_type='text/plain')
    
    logger.warning(f"Webhook verification failed. Token: {token}")
    return HttpResponse('Forbidden', status=403)


def handle_message(request):
    """معالجة الرسائل الواردة من واتساب"""
    try:
        # التحقق من التوقيع
        if not verify_webhook_signature(request):
            logger.warning("Invalid webhook signature")
            return HttpResponse('Invalid signature', status=403)
        
        data = json.loads(request.body)
        
        # استخراج الرسائل
        if 'entry' not in data:
            return HttpResponse('OK')
        
        for entry in data.get('entry', []):
            for change in entry.get('changes', []):
                value = change.get('value', {})
                
                # التحقق من وجود رسائل
                messages = value.get('messages', [])
                if not messages:
                    continue
                
                for message in messages:
                    # استخراج معرف المستخدم (رقم الواتساب) - مهم جداً للعزل
                    user_id = message.get('from')  # رقم الواتساب الفريد
                    message_type = message.get('type')
                    
                    if not user_id:
                        continue
                    
                    # معالجة الرسائل النصية فقط
                    if message_type == 'text':
                        text = message.get('text', {}).get('body', '')
                        if text:
                            # معالجة الرسالة مع user_id الفريد
                            # هذا يضمن عدم تداخل المحادثات
                            response = process_user_message(
                                message=text,
                                user_id=user_id  # رقم الواتساب الفريد لكل عميل
                            )
                            
                            # إرسال الرد
                            send_whatsapp_message(user_id, response)
                    
                    # معالجة الرسائل التفاعلية (الأزرار)
                    elif message_type == 'interactive':
                        interactive = message.get('interactive', {})
                        button_reply = interactive.get('button_reply', {})
                        text = button_reply.get('title', '')
                        if text:
                            response = process_user_message(
                                message=text,
                                user_id=user_id
                            )
                            send_whatsapp_message(user_id, response)
        
        return HttpResponse('OK')
    
    except json.JSONDecodeError:
        logger.error("Invalid JSON in webhook request")
        return HttpResponse('Invalid JSON', status=400)
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return HttpResponse('Error', status=500)


def send_whatsapp_message(to: str, message: str):
    """إرسال رسالة عبر WhatsApp Business API"""
    import requests
    
    if not settings.WHATSAPP_ACCESS_TOKEN or not settings.WHATSAPP_PHONE_NUMBER_ID:
        logger.warning("WhatsApp API not configured")
        return False
    
    url = f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    
    headers = {
        'Authorization': f'Bearer {settings.WHATSAPP_ACCESS_TOKEN}',
        'Content-Type': 'application/json'
    }
    
    payload = {
        'messaging_product': 'whatsapp',
        'recipient_type': 'individual',
        'to': to,
        'type': 'text',
        'text': {
            'preview_url': False,
            'body': message
        }
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        logger.info(f"Message sent to {to}")
        return True
    except requests.RequestException as e:
        logger.error(f"Failed to send message to {to}: {e}")
        return False
