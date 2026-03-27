import httpx
import json
import hashlib
import hmac
import logging
from django.conf import settings
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)


class WhatsAppAPI:
    """
    WhatsApp Business API Client
    للتواصل مع Meta Cloud API
    """
    
    def __init__(self):
        self.access_token = getattr(settings, 'WHATSAPP_ACCESS_TOKEN', '')
        self.phone_number_id = getattr(settings, 'WHATSAPP_PHONE_NUMBER_ID', '')
        self.api_version = getattr(settings, 'WHATSAPP_API_VERSION', 'v18.0')
        self.api_url = f"https://graph.facebook.com/{self.api_version}"
        self.timeout = 30
    
    def _get_headers(self) -> Dict[str, str]:
        return {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
    
    def _make_request(self, endpoint: str, payload: Dict) -> Dict:
        url = f"{self.api_url}/{self.phone_number_id}/{endpoint}"
        
        try:
            response = httpx.post(
                url,
                headers=self._get_headers(),
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            return {'success': True, 'data': response.json()}
        except Exception as e:
            logger.error(f"WhatsApp API Error: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def send_text_message(self, recipient: str, message: str) -> Dict:
        """إرسال رسالة نصية"""
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": message
            }
        }
        return self._make_request("messages", payload)
    
    def send_template_message(
        self,
        recipient: str,
        template_name: str,
        language_code: str = "ar",
        components: Optional[List[Dict]] = None
    ) -> Dict:
        """إرسال رسالة قالب"""
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code}
            }
        }
        
        if components:
            payload["template"]["components"] = components
        
        return self._make_request("messages", payload)
    
    def send_location(
        self,
        recipient: str,
        latitude: float,
        longitude: float,
        name: str,
        address: str
    ) -> Dict:
        """إرسال موقع جغرافي"""
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "location",
            "location": {
                "latitude": latitude,
                "longitude": longitude,
                "name": name,
                "address": address
            }
        }
        return self._make_request("messages", payload)
    
    def send_interactive_buttons(
        self,
        recipient: str,
        body_text: str,
        buttons: List[Dict[str, str]],
        header_text: Optional[str] = None,
        footer_text: Optional[str] = None
    ) -> Dict:
        """إرسال أزرار تفاعلية"""
        interactive = {
            "type": "button",
            "body": {"text": body_text},
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {
                            "id": btn.get("id", f"btn_{i}"),
                            "title": btn.get("title", "")[:20]
                        }
                    }
                    for i, btn in enumerate(buttons[:3])
                ]
            }
        }
        
        if header_text:
            interactive["header"] = {"type": "text", "text": header_text}
        if footer_text:
            interactive["footer"] = {"text": footer_text}
        
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "interactive",
            "interactive": interactive
        }
        return self._make_request("messages", payload)
    
    def send_interactive_list(
        self,
        recipient: str,
        body_text: str,
        button_text: str,
        sections: List[Dict],
        header_text: Optional[str] = None,
        footer_text: Optional[str] = None
    ) -> Dict:
        """إرسال قائمة تفاعلية"""
        interactive = {
            "type": "list",
            "body": {"text": body_text},
            "action": {
                "button": button_text,
                "sections": sections
            }
        }
        
        if header_text:
            interactive["header"] = {"type": "text", "text": header_text}
        if footer_text:
            interactive["footer"] = {"text": footer_text}
        
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "interactive",
            "interactive": interactive
        }
        return self._make_request("messages", payload)
    
    def send_suppliers_list(self, recipient: str, suppliers: List[Dict]) -> Dict:
        """إرسال قائمة الموردين"""
        if not suppliers:
            return self.send_text_message(recipient, "عذراً، لم نجد موردين مطابقين لبحثك.")
        
        sections = [{
            "title": "الموردون المتاحون",
            "rows": [
                {
                    "id": str(s.get('id', i)),
                    "title": s.get('name', '')[:24],
                    "description": f" {s.get('rating', 0)} | {s.get('category', '')}"[:72]
                }
                for i, s in enumerate(suppliers[:10])
            ]
        }]
        
        return self.send_interactive_list(
            recipient=recipient,
            header_text=" نتائج البحث",
            body_text=f"وجدنا {len(suppliers)} مورد. اختر أحدهم للمزيد من التفاصيل:",
            button_text="عرض الموردين",
            sections=sections,
            footer_text="ذيبان - الدليل الذكي"
        )
    
    def send_supplier_details(self, recipient: str, supplier: Dict) -> Dict:
        """إرسال تفاصيل مورد"""
        message = f"""
 *{supplier.get('name', '')}*

 التصنيف: {supplier.get('category', '')}
 التقييم: {supplier.get('rating', 0)}/5
 الهاتف: {supplier.get('phone', 'غير متوفر')}
 ساعات العمل: {supplier.get('hours', 'غير محدد')}

{supplier.get('description', '')}
"""
        result = self.send_text_message(recipient, message.strip())
        
        if supplier.get('location'):
            loc = supplier['location']
            self.send_location(
                recipient,
                loc.get('lat', 0),
                loc.get('lng', 0),
                supplier.get('name', ''),
                loc.get('address', '')
            )
        
        return result
    
    def mark_message_as_read(self, message_id: str) -> Dict:
        """تحديد الرسالة كمقروءة"""
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id
        }
        return self._make_request("messages", payload)


whatsapp_api = WhatsAppAPI()
