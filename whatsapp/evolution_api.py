"""
Evolution API v2 Client
للتكامل مع Evolution API لربط WhatsApp
يدعم: atendai/evolution-api:latest
"""
import httpx
import logging
from django.conf import settings
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)


class EvolutionAPI:
    """
    Client لـ Evolution API v2 (latest)
    يدير إنشاء الجلسة، جلب QR Code، وإرسال الرسائل
    """

    def __init__(self):
        self.base_url = getattr(settings, 'EVOLUTION_API_URL', '').rstrip('/')
        self.api_key = getattr(settings, 'EVOLUTION_API_KEY', '')
        self.instance_name = getattr(settings, 'EVOLUTION_INSTANCE_NAME', 'dhiban')
        self.timeout = 30

    def _headers(self) -> Dict:
        return {
            'apikey': self.api_key,
            'Content-Type': 'application/json',
        }

    def _get(self, path: str) -> Dict:
        url = f"{self.base_url}{path}"
        try:
            resp = httpx.get(url, headers=self._headers(), timeout=self.timeout)
            resp.raise_for_status()
            return {'success': True, 'data': resp.json()}
        except Exception as e:
            status = getattr(getattr(e, 'response', None), 'status_code', 0)
            try:
                body = e.response.json() if hasattr(e, 'response') and e.response else {}
            except Exception:
                body = {}
            logger.error(f"Evolution API GET error [{path}] HTTP {status}: {e}")
            return {'success': False, 'error': str(e), 'status': status, 'body': body}

    def _post(self, path: str, payload: Dict = None) -> Dict:
        url = f"{self.base_url}{path}"
        try:
            resp = httpx.post(
                url,
                headers=self._headers(),
                json=payload or {},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return {'success': True, 'data': resp.json()}
        except Exception as e:
            status = getattr(getattr(e, 'response', None), 'status_code', 0)
            try:
                body = e.response.json() if hasattr(e, 'response') and e.response else {}
            except Exception:
                body = {}
            logger.error(f"Evolution API POST error [{path}] HTTP {status}: {e}")
            return {'success': False, 'error': str(e), 'status': status, 'body': body}

    def _delete(self, path: str) -> Dict:
        url = f"{self.base_url}{path}"
        try:
            resp = httpx.delete(url, headers=self._headers(), timeout=self.timeout)
            resp.raise_for_status()
            return {'success': True, 'data': resp.json()}
        except Exception as e:
            logger.error(f"Evolution API DELETE error [{path}]: {e}")
            return {'success': False, 'error': str(e)}

    # ─── Instance Management ───────────────────────────────────────────────────

    def instance_exists(self) -> bool:
        """التحقق من وجود الـ instance"""
        result = self._get(f'/instance/fetchInstances')
        if result.get('success'):
            instances = result['data']
            if isinstance(instances, list):
                return any(
                    i.get('instance', {}).get('instanceName') == self.instance_name
                    or i.get('instanceName') == self.instance_name
                    for i in instances
                )
        return False

    def create_instance(self) -> Dict:
        """إنشاء instance جديد مع webhook"""
        webhook_url = getattr(settings, 'EVOLUTION_WEBHOOK_URL', '')
        payload = {
            'instanceName': self.instance_name,
            'integration': 'WHATSAPP-BAILEYS',
            'qrcode': True,
        }
        if webhook_url:
            payload['webhook'] = {
                'enabled': True,
                'url': webhook_url,
                'webhook_by_events': False,
                'webhook_base64': True,
                'events': [
                    'MESSAGES_UPSERT',
                    'MESSAGES_UPDATE',
                    'CONNECTION_UPDATE',
                    'QRCODE_UPDATED',
                ],
            }
        return self._post('/instance/create', payload)

    def get_instance_status(self) -> Dict:
        """جلب حالة الاتصال"""
        return self._get(f'/instance/connectionState/{self.instance_name}')

    def get_qrcode(self) -> Dict:
        """جلب QR Code للاتصال"""
        return self._get(f'/instance/connect/{self.instance_name}')

    def extract_qr_base64(self, data: dict) -> Optional[str]:
        """
        استخراج base64 من أي صيغة يعيدها Evolution API latest:
        - { "base64": "data:image/png;base64,..." }
        - { "qrcode": { "base64": "..." } }
        - { "code": "...", "base64": "..." }
        """
        if not data:
            return None
        # صيغة 1: مباشر
        if data.get('base64'):
            b64 = data['base64']
            return b64 if b64.startswith('data:') else f'data:image/png;base64,{b64}'
        # صيغة 2: متداخل في qrcode
        qr = data.get('qrcode', {})
        if isinstance(qr, dict) and qr.get('base64'):
            b64 = qr['base64']
            return b64 if b64.startswith('data:') else f'data:image/png;base64,{b64}'
        # صيغة 3: في instance.qrcode
        inst = data.get('instance', {})
        if isinstance(inst, dict):
            qr2 = inst.get('qrcode', {})
            if isinstance(qr2, dict) and qr2.get('base64'):
                b64 = qr2['base64']
                return b64 if b64.startswith('data:') else f'data:image/png;base64,{b64}'
        return None

    def get_or_create_qrcode(self) -> Optional[str]:
        """
        يحاول جلب QR Code، وإذا لم يجد الـ instance ينشئه أولاً.
        يعيد base64 string أو None.
        """
        import time

        # أولاً: جرب جلب الـ QR مباشرة
        result = self.get_qrcode()
        if result.get('success'):
            qr = self.extract_qr_base64(result['data'])
            if qr:
                return qr

        # ثانياً: أي فشل (404, 400, connection error) — حاول إنشاء الـ instance
        logger.info(f"QR fetch failed ({result.get('error', '')}), attempting to create instance...")
        create_result = self.create_instance()

        if create_result.get('success'):
            qr = self.extract_qr_base64(create_result['data'])
            if qr:
                return qr
            # أحياناً لا يأتي QR مع الإنشاء — انتظر ثم اجلبه
            time.sleep(3)
            result2 = self.get_qrcode()
            if result2.get('success'):
                return self.extract_qr_base64(result2['data'])

        elif '422' in str(create_result.get('error', '')) or 'already' in str(create_result.get('body', '')).lower():
            # الـ instance موجود مسبقاً — فقط اجلب الـ QR
            logger.info("Instance already exists, fetching QR...")
            time.sleep(1)
            result3 = self.get_qrcode()
            if result3.get('success'):
                return self.extract_qr_base64(result3['data'])

        return None

    def logout_instance(self) -> Dict:
        """قطع الاتصال (logout)"""
        return self._delete(f'/instance/logout/{self.instance_name}')

    def delete_instance(self) -> Dict:
        """حذف الـ instance"""
        return self._delete(f'/instance/delete/{self.instance_name}')

    def restart_instance(self) -> Dict:
        """إعادة تشغيل الـ instance"""
        return self._post(f'/instance/restart/{self.instance_name}')

    def is_connected(self) -> bool:
        """التحقق من حالة الاتصال - يدعم جميع صيغ v2.x"""
        try:
            result = self.get_instance_status()
            if result.get('success'):
                data = result['data']
                # صيغة 1: { "instance": { "state": "open" } }
                state = data.get('instance', {}).get('state', '')
                # صيغة 2: { "state": "open" }
                if not state:
                    state = data.get('state', '')
                # صيغة 3: { "connectionStatus": "open" }
                if not state:
                    state = data.get('connectionStatus', '')
                # صيغة 4: قائمة instances
                if not state and isinstance(data, list):
                    for inst in data:
                        if inst.get('instance', {}).get('instanceName') == self.instance_name:
                            state = inst.get('instance', {}).get('connectionStatus', '') or inst.get('instance', {}).get('state', '')
                            break
                return state in ('open', 'connected', 'CONNECTED')
        except Exception as e:
            logger.error(f"is_connected error: {e}")
        return False

    # ─── Messaging ─────────────────────────────────────────────────────────────

    def send_text(self, phone: str, message: str, link_preview: bool = True) -> Dict:
        """إرسال رسالة نصية مع دعم معاينة الروابط"""
        phone = self._normalize_phone(phone)
        payload = {
            'number': phone,
            'text': message,
            'linkPreview': link_preview,
        }
        result = self._post(f'/message/sendText/{self.instance_name}', payload)
        if not result.get('success'):
            logger.error(f"send_text failed to {phone}: {result.get('error')}")
        return result

    def send_url_button(self, phone: str, body: str, button_text: str, url: str, footer: str = '') -> Dict:
        """
        إرسال رسالة مع زر URL تفاعلي.
        عند الضغط على الزر يفتح الرابط مباشرة (مثل: خريطة Google Maps).
        يستخدم صيغة Evolution API v2: /message/sendButtons
        """
        phone = self._normalize_phone(phone)
        payload = {
            'number': phone,
            'title': '',
            'description': body,
            'footer': footer,
            'buttons': [
                {
                    'type': 'url',
                    'displayText': button_text,
                    'url': url,
                }
            ],
        }
        result = self._post(f'/message/sendButtons/{self.instance_name}', payload)
        if not result.get('success'):
            # fallback: نص عادي مع الرابط
            logger.warning(f"send_url_button failed ({result.get('error')}), falling back to text")
            fallback = f"{body}\n\n🗺️ {button_text}:\n{url}"
            return self.send_text(phone, fallback, link_preview=True)
        return result

    def send_image(self, phone: str, image_url: str, caption: str = '') -> Dict:
        """إرسال صورة"""
        phone = self._normalize_phone(phone)
        payload = {
            'number': phone,
            'mediatype': 'image',
            'mimetype': 'image/jpeg',
            'caption': caption,
            'media': image_url,
        }
        return self._post(f'/message/sendMedia/{self.instance_name}', payload)

    # ─── Media ───────────────────────────────────────────────────────────────────

    def download_media_base64(self, message_key_id: str, remote_jid: str = '') -> Optional[str]:
        """
        تحميل وسائط من Evolution API وإرجاعها كـ base64.
        endpoint: POST /chat/getBase64FromMediaMessage/{instance}
        
        Per API docs, payload must be: { "message": { "key": { "id": "..." } } }
        """
        # الصيغة الصحيحة حسب التوثيق الرسمي v2
        key_obj = {'id': message_key_id}
        if remote_jid:
            key_obj['remoteJid'] = remote_jid
        
        payload = {
            'message': {
                'key': key_obj,
            },
            'convertToMp4': False,
        }
        
        logger.info(f"[EVOLUTION-API] Downloading media base64 for message {message_key_id}")
        result = self._post(
            f'/chat/getBase64FromMediaMessage/{self.instance_name}',
            payload
        )
        
        if result.get('success'):
            data = result.get('data', {})
            # Evolution API يعيد: { "base64": "...", "mimetype": "..." }
            b64 = data.get('base64', '')
            if b64:
                logger.info(f"[EVOLUTION-API] Got media base64, length={len(b64)}")
                return b64
            # بعض الإصدارات تعيد مباشرة كـ string
            if isinstance(data, str) and len(data) > 100:
                logger.info(f"[EVOLUTION-API] Got media base64 as direct string, length={len(data)}")
                return data
        
        logger.error(f"[EVOLUTION-API] Failed to download media base64: {result.get('error', 'unknown')} | status={result.get('status')}")
        
        # محاولة ثانية بالصيغة القديمة (بدون message wrapper)
        payload_old = {
            'key': {'id': message_key_id},
            'convertToMp4': False,
        }
        if remote_jid:
            payload_old['key']['remoteJid'] = remote_jid
        
        logger.info(f"[EVOLUTION-API] Retrying with old payload format...")
        result2 = self._post(
            f'/chat/getBase64FromMediaMessage/{self.instance_name}',
            payload_old
        )
        if result2.get('success'):
            data2 = result2.get('data', {})
            b64 = data2.get('base64', '')
            if b64:
                logger.info(f"[EVOLUTION-API] Got media base64 (old format), length={len(b64)}")
                return b64
        
        logger.error(f"[EVOLUTION-API] Both download attempts failed for message {message_key_id}")
        return None

    # ─── Webhook Setup ──────────────────────────────────────────────────────────

    def set_webhook(self, webhook_url: str) -> Dict:
        """تعيين webhook URL مع تفعيل base64 لاستقبال الوسائط"""
        # Evolution API v2.3.x يتطلب الحقول ملفوفة داخل "webhook" object
        # بدونه يرجع 400: "instance requires property webhook"
        webhook_config = {
            'enabled': True,
            'url': webhook_url,
            'webhook_by_events': False,
            'webhook_base64': True,
            'events': [
                'MESSAGES_UPSERT',
                'MESSAGES_UPDATE',
                'CONNECTION_UPDATE',
                'QRCODE_UPDATED',
            ],
        }
        
        # الصيغة الصحيحة لـ v2.3.x: ملفوفة في webhook object
        payload = {'webhook': webhook_config}
        
        logger.info(f"[EVOLUTION-API] Setting webhook (wrapped format): {webhook_url}, base64=True")
        result = self._post(f'/webhook/set/{self.instance_name}', payload)
        
        if result.get('success'):
            logger.info(f"[EVOLUTION-API] Webhook set successfully!")
            return result
        
        # إذا فشلت الصيغة الملفوفة، جرب الصيغة المباشرة (لإصدارات أحدث)
        logger.warning(f"[EVOLUTION-API] Wrapped format failed, trying flat format...")
        result2 = self._post(f'/webhook/set/{self.instance_name}', webhook_config)
        if result2.get('success'):
            logger.info(f"[EVOLUTION-API] Webhook set with flat format!")
            return result2
        
        logger.error(f"[EVOLUTION-API] Both webhook formats failed! wrapped={result.get('error')} flat={result2.get('error')}")
        return result

    # ─── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        """تنسيق رقم الهاتف — يزيل + والمسافات والشرطات"""
        return phone.strip().replace('+', '').replace(' ', '').replace('-', '')


# Singleton instance
evolution_api = EvolutionAPI()
