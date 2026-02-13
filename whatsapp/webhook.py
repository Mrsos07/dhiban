import json
import hashlib
import hmac
import logging
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings
from django.utils import timezone

from users.models import WhatsAppUser
from conversations.models import Conversation
from .api import whatsapp_api

logger = logging.getLogger(__name__)


def verify_webhook_signature(request) -> bool:
    """التحقق من توقيع Meta"""
    signature = request.headers.get('X-Hub-Signature-256', '')
    
    if not signature:
        return False
    
    app_secret = getattr(settings, 'WHATSAPP_APP_SECRET', '')
    if not app_secret:
        logger.warning("WHATSAPP_APP_SECRET not configured")
        return True
    
    expected_signature = 'sha256=' + hmac.new(
        app_secret.encode('utf-8'),
        request.body,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(signature, expected_signature)


def extract_message_data(data: dict) -> dict:
    """استخراج بيانات الرسالة من payload"""
    try:
        entry = data.get('entry', [{}])[0]
        changes = entry.get('changes', [{}])[0]
        value = changes.get('value', {})
        
        messages = value.get('messages', [])
        if not messages:
            return None
        
        message = messages[0]
        contact = value.get('contacts', [{}])[0]
        
        return {
            'message_id': message.get('id'),
            'from': message.get('from'),
            'timestamp': message.get('timestamp'),
            'type': message.get('type'),
            'text': message.get('text', {}).get('body', ''),
            'contact_name': contact.get('profile', {}).get('name', ''),
            'button_reply': message.get('interactive', {}).get('button_reply', {}),
            'list_reply': message.get('interactive', {}).get('list_reply', {}),
            'location': message.get('location', {}),
        }
    except (KeyError, IndexError) as e:
        logger.error(f"Error extracting message data: {e}")
        return None


def get_or_create_user(phone_number: str, name: str = '') -> WhatsAppUser:
    """الحصول على المستخدم أو إنشاؤه"""
    user, created = WhatsAppUser.objects.get_or_create(
        phone_number=phone_number,
        defaults={
            'whatsapp_id': phone_number,
            'name': name,
        }
    )
    
    if not created:
        user.update_last_interaction()
        if name and not user.name:
            user.name = name
            user.save(update_fields=['name'])
    
    return user


def get_or_create_conversation(user: WhatsAppUser) -> Conversation:
    """الحصول على محادثة نشطة أو إنشاء جديدة"""
    recent_conversation = Conversation.objects.filter(
        user=user,
        ended_at__isnull=True,
        started_at__gte=timezone.now() - timezone.timedelta(hours=24)
    ).first()
    
    if recent_conversation:
        return recent_conversation
    
    return Conversation.objects.create(user=user)


def process_incoming_message(message_data: dict):
    """معالجة الرسالة الواردة باستخدام وكيل الذكاء الاصطناعي"""
    phone_number = message_data.get('from')
    text = message_data.get('text', '')
    contact_name = message_data.get('contact_name', '')
    
    user = get_or_create_user(phone_number, contact_name)
    conversation = get_or_create_conversation(user)
    
    # حفظ رسالة المستخدم
    conversation.add_message('user', text)
    
    # تحديد الرسالة كمقروءة
    whatsapp_api.mark_message_as_read(message_data.get('message_id'))
    
    # معالجة الرد
    if message_data.get('button_reply'):
        button_id = message_data['button_reply'].get('id', '')
        response = handle_button_reply(user, conversation, button_id)
    elif message_data.get('list_reply'):
        list_id = message_data['list_reply'].get('id', '')
        response = handle_list_reply(user, conversation, list_id)
    elif text:
        response = handle_text_message(user, conversation, text)
    else:
        response = "عذرا لم أفهم رسالتك. أرسل لي نص أو اختر من القائمة."
    
    # إرسال الرد
    if response:
        whatsapp_api.send_text_message(phone_number, response)
        conversation.add_message('bot', response)
    
    return True


def handle_text_message(user: WhatsAppUser, conversation: Conversation, text: str) -> str:
    """معالجة الرسالة النصية باستخدام وكيل الذكاء الاصطناعي"""
    text_lower = text.lower().strip()
    
    # التحقق من رسائل الترحيب
    greetings = ['مرحبا', 'السلام عليكم', 'هلا', 'اهلا', 'hi', 'hello', 'ابدأ', 'start']
    if any(g in text_lower for g in greetings):
        # إرسال رسالة ترحيب مع أزرار
        whatsapp_api.send_interactive_buttons(
            recipient=user.phone_number,
            header_text="مرحبا بك في ذيبان! ",
            body_text="أنا دليلك الذكي في عنيزة!\n\nأقدر أساعدك تلقى أي خدمة تحتاجها. فقط قل لي وش تبي!",
            buttons=[
                {"id": "search", "title": " ابحث لي"},
                {"id": "categories", "title": " التصنيفات"},
                {"id": "help", "title": " مساعدة"}
            ],
            footer_text="ذيبان - الدليل الذكي"
        )
        return None  # لا نرسل رسالة نصية إضافية
    
    # استخدام وكيل الذكاء الاصطناعي
    # نستخدم رقم الواتساب كـ user_id لضمان عزل المحادثات
    try:
        from ai_agent.agent import process_user_message
        response = process_user_message(text, user.phone_number)
        
        # تحديث نوع المحادثة
        conversation.intent_detected = 'search'
        conversation.save(update_fields=['intent_detected'])
        
        return response
    except Exception as e:
        logger.error(f"AI Agent error: {e}")
        return "عذرا حدث خطأ. جرب مرة ثانية أو أرسل 'مساعدة' للمزيد من الخيارات."


def handle_button_reply(user: WhatsAppUser, conversation: Conversation, button_id: str) -> str:
    """معالجة الرد على الأزرار"""
    if button_id == 'search':
        return "تمام! قل لي وش تبحث عنه\n\nمثال:\n- أبي كهربائي\n- وين أقرب مطعم\n- محل جوالات"
    
    elif button_id == 'categories':
        send_categories_list(user.phone_number)
        return None
    
    elif button_id == 'help':
        return """ *كيف تستخدم ذيبان*

1 اكتب ما تحتاجه بكلماتك
   مثال: "أبي سباك يصلح المغسلة"

2 أو اختر من التصنيفات

3 راح أرسل لك أفضل الخيارات!

 *نصيحة:* كل ما كان وصفك أدق كل ما كانت النتيجة أفضل!"""
    
    return "اختر من القائمة أو اكتب ما تحتاجه."


def handle_list_reply(user: WhatsAppUser, conversation: Conversation, list_id: str) -> str:
    """معالجة الرد على القائمة"""
    # البحث في التصنيف المختار
    # نستخدم رقم الواتساب كـ user_id لضمان عزل المحادثات
    try:
        from ai_agent.agent import process_user_message
        response = process_user_message(f"أبي {list_id}", user.phone_number)
        return response
    except Exception as e:
        logger.error(f"List reply error: {e}")
        return f"جاري البحث في {list_id}..."


def send_categories_list(phone_number: str):
    """إرسال قائمة التصنيفات"""
    from suppliers.models import Category
    
    categories = Category.objects.filter(is_active=True)[:10]
    
    if not categories:
        whatsapp_api.send_text_message(phone_number, "لا توجد تصنيفات متاحة حاليا.")
        return
    
    sections = [{
        "title": "التصنيفات المتاحة",
        "rows": [
            {
                "id": cat.name_ar,
                "title": cat.name_ar[:24],
                "description": f"البحث في {cat.name_ar}"[:72]
            }
            for cat in categories
        ]
    }]
    
    whatsapp_api.send_interactive_list(
        recipient=phone_number,
        header_text=" التصنيفات",
        body_text="اختر التصنيف اللي تبحث فيه:",
        button_text="عرض التصنيفات",
        sections=sections
    )


@csrf_exempt
@require_http_methods(["GET", "POST"])
def webhook_handler(request):
    """معالج Webhook الرئيسي"""
    
    if request.method == "GET":
        mode = request.GET.get('hub.mode')
        token = request.GET.get('hub.verify_token')
        challenge = request.GET.get('hub.challenge')
        
        verify_token = getattr(settings, 'WHATSAPP_VERIFY_TOKEN', '')
        
        if mode == 'subscribe' and token == verify_token:
            logger.info("Webhook verified successfully")
            return HttpResponse(challenge, content_type='text/plain')
        else:
            logger.warning("Webhook verification failed")
            return HttpResponse('Forbidden', status=403)
    
    if request.method == "POST":
        if not verify_webhook_signature(request):
            logger.warning("Invalid webhook signature")
            return HttpResponse('Unauthorized', status=401)
        
        try:
            data = json.loads(request.body)
            logger.info(f"Received webhook: {json.dumps(data, indent=2)}")
            
            message_data = extract_message_data(data)
            
            if message_data:
                process_incoming_message(message_data)
            
            return HttpResponse('OK', status=200)
        
        except json.JSONDecodeError:
            logger.error("Invalid JSON in webhook")
            return HttpResponse('Bad Request', status=400)
        except Exception as e:
            logger.error(f"Webhook processing error: {e}")
            return HttpResponse('OK', status=200)
    
    return HttpResponse('Method Not Allowed', status=405)
