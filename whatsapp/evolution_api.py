"""
Evolution API v2 Client
للتكامل مع Evolution API لربط WhatsApp
"""
import requests
import logging
from django.conf import settings
from typing import Optional, Dict

logger = logging.getLogger(__name__)


class EvolutionAPI:
    """
    Client لـ Evolution API v2
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

    def create_instance(self) -> Dict:
        """إنشاء instance جديد"""
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
        result = self.get_instance_status()
        if result.get('success'):
            state = result['data'].get('instance', {}).get('state', '')
            return state == 'open'
        return False

    # ─── Messaging ─────────────────────────────────────────────────────────────

    def send_text(self, phone: str, message: str) -> Dict:
        """إرسال رسالة نصية"""
        phone = self._normalize_phone(phone)
        payload = {
            'number': phone,
            'text': message,
        }
        return self._post(f'/message/sendText/{self.instance_name}', payload)

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

    def send_buttons(self, phone: str, text: str, buttons: list, title: str = '') -> Dict:
        """إرسال أزرار تفاعلية"""
        phone = self._normalize_phone(phone)
        payload = {
            'number': phone,
            'title': title,
            'description': text,
            'footer': 'ذيبان - الدليل الذكي',
            'buttons': [
                {'type': 'reply', 'displayText': btn.get('title', ''), 'id': btn.get('id', '')}
                for btn in buttons[:3]
            ],
        }
        return self._post(f'/message/sendButtons/{self.instance_name}', payload)

    # ─── Webhook Setup ──────────────────────────────────────────────────────────

    def set_webhook(self, webhook_url: str) -> Dict:
        """تعيين webhook URL"""
        payload = {
            'webhook': {
                'enabled': True,
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
        }
        return self._post(f'/webhook/set/{self.instance_name}', payload)

    # ─── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        """تنسيق رقم الهاتف — يزيل + ويضيف كود الدولة إذا لزم"""
        phone = phone.strip().replace('+', '').replace(' ', '').replace('-', '')
        return phone


# Singleton instance
evolution_api = EvolutionAPI()
