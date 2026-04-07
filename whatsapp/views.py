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

from ai_agent.agent import process_user_message, dhiban_agent

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
                    
                    # معالجة الرسائل النصية
                    if message_type == 'text':
                        text = message.get('text', {}).get('body', '')
                        if text:
                            response = process_user_message(
                                message=text,
                                user_id=user_id
                            )
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
                    
                    # معالجة الصور
                    elif message_type == 'image':
                        img = message.get('image', {})
                        media_id = img.get('id', '')
                        logger.info(f"[VIEWS] Image message from {user_id}, media_id={media_id}, mime={img.get('mime_type')}")
                        if media_id:
                            try:
                                image_base64 = _download_media_base64(media_id)
                                if image_base64:
                                    logger.info(f"[VIEWS] Downloaded image base64, length={len(image_base64)}")
                                    response = dhiban_agent.process_image_message(
                                        user_id=user_id,
                                        image_base64=image_base64,
                                        mime_type=img.get('mime_type', 'image/jpeg'),
                                        caption=img.get('caption', ''),
                                    )
                                else:
                                    logger.error(f"[VIEWS] Failed to download image base64 for media_id={media_id}")
                                    response = "ما قدرت أحمّل الصورة 😕 جرب مرة ثانية!"
                                send_whatsapp_message(user_id, response)
                            except Exception as e:
                                logger.error(f"[VIEWS] Image processing error: {e}", exc_info=True)
                                send_whatsapp_message(user_id, "صار خطأ في تحليل الصورة 😕 جرب مرة ثانية!")
                    
                    # معالجة الرسائل الصوتية
                    elif message_type in ('audio', 'voice'):
                        aud = message.get('audio', message.get('voice', {}))
                        media_id = aud.get('id', '')
                        if media_id:
                            try:
                                media_url = _get_media_url(media_id)
                                if media_url:
                                    download_headers = {
                                        'Authorization': f'Bearer {settings.WHATSAPP_ACCESS_TOKEN}'
                                    }
                                    response = dhiban_agent.process_voice_message(
                                        user_id=user_id,
                                        audio_url=media_url,
                                        mime_type=aud.get('mime_type', 'audio/ogg'),
                                        download_headers=download_headers,
                                    )
                                else:
                                    response = "ما قدرت أحمّل الرسالة الصوتية 😕 اكتب لي بدالها!"
                                send_whatsapp_message(user_id, response)
                            except Exception as e:
                                logger.error(f"Audio processing error: {e}")
                                send_whatsapp_message(user_id, "صار خطأ في تحليل الصوت 😕 جرب مرة ثانية!")
        
        return HttpResponse('OK')
    
    except json.JSONDecodeError:
        logger.error("Invalid JSON in webhook request")
        return HttpResponse('Invalid JSON', status=400)
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return HttpResponse('Error', status=500)


def _get_media_url(media_id: str) -> str:
    """الحصول على رابط تحميل الوسائط من Meta API"""
    import httpx
    
    url = f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/{media_id}"
    headers = {
        'Authorization': f'Bearer {settings.WHATSAPP_ACCESS_TOKEN}',
    }
    try:
        response = httpx.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data.get('url', '')
    except Exception as e:
        logger.error(f"Failed to get media URL for {media_id}: {e}")
        return ''


def _download_media_base64(media_id: str) -> str:
    """تحميل الوسائط من Meta API وتحويلها لـ base64"""
    import httpx
    import base64
    
    media_url = _get_media_url(media_id)
    if not media_url:
        return ''
    
    headers = {
        'Authorization': f'Bearer {settings.WHATSAPP_ACCESS_TOKEN}',
    }
    try:
        response = httpx.get(media_url, headers=headers, timeout=60, follow_redirects=True)
        response.raise_for_status()
        return base64.b64encode(response.content).decode('utf-8')
    except Exception as e:
        logger.error(f"Failed to download media: {e}")
        return ''


def send_whatsapp_message(to: str, message: str):
    """إرسال رسالة عبر WhatsApp Business API"""
    import httpx
    
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
        response = httpx.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        logger.info(f"Message sent to {to}")
        return True
    except Exception as e:
        logger.error(f"Failed to send message to {to}: {e}")
        return False
