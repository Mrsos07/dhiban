"""
Evolution API v2 Client
للتكامل مع Evolution API لربط WhatsApp
يدعم: atendai/evolution-api:latest
"""
import requests
import requests.exceptions
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
            resp = requests.get(url, headers=self._headers(), timeout=self.timeout)
            resp.raise_for_status()
            return {'success': True, 'data': resp.json()}
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else 0
            try:
                body = e.response.json()
            except Exception:
                body = {}
            logger.error(f"Evolution API GET HTTP {status} [{path}]: {body}")
            return {'success': False, 'error': str(e), 'status': status, 'body': body}
        except requests.exceptions.RequestException as e:
            logger.error(f"Evolution API GET error [{path}]: {e}")
            return {'success': False, 'error': str(e)}

    def _post(self, path: str, payload: Dict = None) -> Dict:
        url = f"{self.base_url}{path}"
        try:
            resp = requests.post(
                url,
                headers=self._headers(),
                json=payload or {},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return {'success': True, 'data': resp.json()}
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else 0
            try:
                body = e.response.json()
            except Exception:
                body = {}
            logger.error(f"Evolution API POST HTTP {status} [{path}]: {body}")
            return {'success': False, 'error': str(e), 'status': status, 'body': body}
        except requests.exceptions.RequestException as e:
            logger.error(f"Evolution API POST error [{path}]: {e}")
            return {'success': False, 'error': str(e)}

    def _delete(self, path: str) -> Dict:
        url = f"{self.base_url}{path}"
        try:
            resp = requests.delete(url, headers=self._headers(), timeout=self.timeout)
            resp.raise_for_status()
            return {'success': True, 'data': resp.json()}
        except requests.exceptions.RequestException as e:
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
                'url': webhook_url,
                'byEvents': False,
                'base64': False,
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
        # أولاً: جرب جلب الـ QR مباشرة
        result = self.get_qrcode()
        if result.get('success'):
            qr = self.extract_qr_base64(result['data'])
            if qr:
                return qr

        # ثانياً: إذا 404 أو instance غير موجود — أنشئه
        status_code = result.get('status', 0)
        if status_code in (404, 400) or not result.get('success'):
            logger.info("Instance not found, creating...")
            create_result = self.create_instance()
            if create_result.get('success'):
                qr = self.extract_qr_base64(create_result['data'])
                if qr:
                    return qr
                # أحياناً لا يأتي QR مع الإنشاء — نجلبه بعدها
                import time
                time.sleep(2)
                result2 = self.get_qrcode()
                if result2.get('success'):
                    return self.extract_qr_base64(result2['data'])

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
        """التحقق من حالة الاتصال"""
        try:
            result = self.get_instance_status()
            if result.get('success'):
                data = result['data']
                # صيغة: { "instance": { "state": "open" } }
                state = data.get('instance', {}).get('state', '')
                if not state:
                    # صيغة بديلة: { "state": "open" }
                    state = data.get('state', '')
                return state == 'open'
        except Exception as e:
            logger.error(f"is_connected error: {e}")
        return False

    # ─── Messaging ─────────────────────────────────────────────────────────────

    def send_text(self, phone: str, message: str) -> Dict:
        """إرسال رسالة نصية"""
        phone = self._normalize_phone(phone)
        payload = {
            'number': phone,
            'text': message,
        }
        result = self._post(f'/message/sendText/{self.instance_name}', payload)
        if not result.get('success'):
            logger.error(f"send_text failed to {phone}: {result.get('error')}")
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

    # ─── Webhook Setup ──────────────────────────────────────────────────────────

    def set_webhook(self, webhook_url: str) -> Dict:
        """تعيين webhook URL"""
        payload = {
            'url': webhook_url,
            'byEvents': False,
            'base64': False,
            'events': [
                'MESSAGES_UPSERT',
                'MESSAGES_UPDATE',
                'CONNECTION_UPDATE',
                'QRCODE_UPDATED',
            ],
        }
        return self._post(f'/webhook/set/{self.instance_name}', payload)

    # ─── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        """تنسيق رقم الهاتف — يزيل + والمسافات والشرطات"""
        return phone.strip().replace('+', '').replace(' ', '').replace('-', '')


# Singleton instance
evolution_api = EvolutionAPI()
