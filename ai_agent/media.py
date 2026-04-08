"""
معالجة الوسائط: تحليل الصور بـ OpenAI Vision وتحويل الصوت بـ Whisper
"""
import io
import base64
import logging
import tempfile
import httpx
from typing import Optional, Dict
from openai import OpenAI

from .config import OPENAI_API_KEY

logger = logging.getLogger(__name__)

# OpenAI client
_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# ─── Image Analysis ─────────────────────────────────────────────────────────

IMAGE_ANALYSIS_PROMPT = """أنت مساعد ذكي متخصص في التعرف على المنتجات والأشياء في الصور.

مهمتك:
1. حدد بدقة ما هو الشيء/المنتج في الصورة
2. أعطِ اسم المنتج بالعربي والإنجليزي
3. حدد نوع المتجر أو المكان الذي يُباع فيه هذا المنتج (مثل: سوبرماركت، محل إلكترونيات، صيدلية، محل عطور، مكتبة، محل جوالات، إلخ)
4. أعطِ كلمة بحث مناسبة للبحث عنه في Google Maps

أجب بصيغة JSON فقط بدون أي نص إضافي:
{
    "product_name_ar": "اسم المنتج بالعربي",
    "product_name_en": "product name in English",
    "category": "نوع المتجر بالعربي (مثل: سوبرماركت، صيدلية، محل إلكترونيات)",
    "search_query": "كلمة بحث للبحث في Google Maps عن مكان بيع المنتج في عنيزة",
    "google_place_type": "نوع المكان في Google مثل: store, pharmacy, supermarket, electronics_store",
    "description": "وصف مختصر للمنتج بالعربي"
}

إذا كانت الصورة ليست منتج (مثل: مكان، طبيعة، شخص) أجب:
{
    "product_name_ar": "",
    "product_name_en": "",
    "category": "",
    "search_query": "",
    "google_place_type": "",
    "description": "وصف ما تراه في الصورة بالعربي",
    "is_product": false
}
"""


def analyze_image_from_url(image_url: str) -> Optional[Dict]:
    """
    تحليل صورة من رابط URL باستخدام OpenAI Vision (GPT-4o)
    
    Args:
        image_url: رابط الصورة المباشر
    
    Returns:
        dict مع معلومات المنتج أو None
    """
    if not _client:
        logger.error("OpenAI client not configured for image analysis")
        return None
    
    try:
        logger.info(f"[MEDIA] Analyzing image from URL: {image_url[:100]}")
        
        response = _client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": IMAGE_ANALYSIS_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": image_url,
                                "detail": "high"
                            }
                        }
                    ]
                }
            ],
            max_tokens=500,
            temperature=0.3
        )
        
        result_text = response.choices[0].message.content.strip()
        logger.info(f"[MEDIA] Vision response: {result_text[:200]}")
        
        # تنظيف JSON من markdown code blocks
        if result_text.startswith("```"):
            result_text = result_text.split("\n", 1)[1] if "\n" in result_text else result_text[3:]
            if result_text.endswith("```"):
                result_text = result_text[:-3]
            result_text = result_text.strip()
        
        import json
        result = json.loads(result_text)
        return result
        
    except Exception as e:
        logger.error(f"[MEDIA] Image analysis error: {e}", exc_info=True)
        return None


def analyze_image_from_base64(image_base64: str, mime_type: str = "image/jpeg") -> Optional[Dict]:
    """
    تحليل صورة من base64 باستخدام OpenAI Vision
    
    Args:
        image_base64: الصورة مشفرة بـ base64
        mime_type: نوع الصورة
    
    Returns:
        dict مع معلومات المنتج أو None
    """
    if not _client:
        logger.error("[MEDIA] OpenAI client not configured for image analysis")
        return None
    
    if not image_base64:
        logger.error("[MEDIA] Empty base64 string received")
        return None
    
    try:
        import json as json_mod
        
        # تنظيف base64 — إزالة أي prefix مثل data:image/jpeg;base64,
        clean_base64 = image_base64
        if "base64," in clean_base64:
            clean_base64 = clean_base64.split("base64,")[1]
        
        # إزالة whitespace و newlines
        clean_base64 = clean_base64.strip().replace('\n', '').replace('\r', '').replace(' ', '')
        
        logger.info(f"[MEDIA] Base64 length: {len(clean_base64)}, first 50 chars: {clean_base64[:50]}")
        
        # التحقق من صحة base64
        try:
            test_decode = base64.b64decode(clean_base64[:100] + '==')
            logger.info(f"[MEDIA] Base64 validation OK, decoded sample: {len(test_decode)} bytes")
        except Exception as e:
            logger.error(f"[MEDIA] Base64 validation FAILED: {e}")
            # محاولة إصلاح base64 padding
            padding = 4 - len(clean_base64) % 4
            if padding != 4:
                clean_base64 += '=' * padding
                logger.info(f"[MEDIA] Added {padding} padding chars")
        
        # تحديد mime_type إذا كان غريب
        if ';' in mime_type:
            mime_type = mime_type.split(';')[0].strip()
        if not mime_type or mime_type == 'application/octet-stream':
            mime_type = 'image/jpeg'
        
        data_url = f"data:{mime_type};base64,{clean_base64}"
        
        logger.info(f"[MEDIA] Sending to OpenAI Vision (model=gpt-4o, mime={mime_type}, data_url_len={len(data_url)})")
        
        response = _client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": IMAGE_ANALYSIS_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": data_url,
                                "detail": "low"
                            }
                        }
                    ]
                }
            ],
            max_tokens=500,
            temperature=0.3
        )
        
        result_text = response.choices[0].message.content.strip()
        logger.info(f"[MEDIA] Vision raw response: {result_text[:500]}")
        
        # تنظيف JSON من markdown code blocks
        cleaned = result_text
        if cleaned.startswith("```"):
            # إزالة السطر الأول (```json أو ```)
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:])
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
        
        # محاولة إيجاد JSON في النص حتى لو كان محاط بنص عادي
        if not cleaned.startswith('{'):
            start = cleaned.find('{')
            end = cleaned.rfind('}')
            if start != -1 and end != -1:
                cleaned = cleaned[start:end+1]
        
        logger.info(f"[MEDIA] Cleaned JSON: {cleaned[:300]}")
        
        result = json_mod.loads(cleaned)
        logger.info(f"[MEDIA] Analysis result: product={result.get('product_name_ar', 'N/A')}, category={result.get('category', 'N/A')}")
        return result
        
    except Exception as e:
        logger.error(f"[MEDIA] Image analysis (base64) error: {type(e).__name__}: {e}", exc_info=True)
        return None


def download_image_as_base64(url: str, headers: dict = None) -> Optional[str]:
    """
    تحميل صورة من URL وتحويلها إلى base64
    """
    try:
        resp = httpx.get(url, headers=headers or {}, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        return base64.b64encode(resp.content).decode('utf-8')
    except Exception as e:
        logger.error(f"[MEDIA] Failed to download image: {e}")
        return None


# ─── Voice Transcription ────────────────────────────────────────────────────

def transcribe_audio_from_url(audio_url: str, headers: dict = None) -> Optional[str]:
    """
    تحميل ملف صوتي من URL وتحويله لنص باستخدام OpenAI Whisper
    
    Args:
        audio_url: رابط الملف الصوتي
        headers: headers إضافية للتحميل (مثل Authorization)
    
    Returns:
        النص المستخرج أو None
    """
    if not _client:
        logger.error("OpenAI client not configured for transcription")
        return None
    
    try:
        logger.info(f"[MEDIA] Downloading audio from: {audio_url[:100]}")
        
        # تحميل الملف الصوتي
        resp = httpx.get(audio_url, headers=headers or {}, timeout=60, follow_redirects=True)
        resp.raise_for_status()
        audio_bytes = resp.content
        
        logger.info(f"[MEDIA] Audio downloaded, size: {len(audio_bytes)} bytes")
        
        return transcribe_audio_bytes(audio_bytes)
        
    except Exception as e:
        logger.error(f"[MEDIA] Audio download/transcription error: {e}", exc_info=True)
        return None


def transcribe_audio_from_base64(audio_base64: str, mime_type: str = "audio/ogg") -> Optional[str]:
    """
    تحويل صوت من base64 إلى نص
    
    Args:
        audio_base64: الصوت مشفر بـ base64
        mime_type: نوع الملف الصوتي
    
    Returns:
        النص المستخرج أو None
    """
    if not _client:
        logger.error("OpenAI client not configured for transcription")
        return None
    
    try:
        # تنظيف base64
        if "base64," in audio_base64:
            audio_base64 = audio_base64.split("base64,")[1]
        
        audio_bytes = base64.b64decode(audio_base64)
        return transcribe_audio_bytes(audio_bytes, mime_type)
        
    except Exception as e:
        logger.error(f"[MEDIA] Audio base64 transcription error: {e}", exc_info=True)
        return None


def transcribe_audio_bytes(audio_bytes: bytes, mime_type: str = "audio/ogg") -> Optional[str]:
    """
    تحويل بايتات صوتية لنص باستخدام Whisper
    """
    if not _client:
        return None
    
    try:
        # تحديد امتداد الملف حسب نوع MIME
        ext_map = {
            "audio/ogg": "ogg",
            "audio/opus": "ogg",
            "audio/ogg; codecs=opus": "ogg",
            "audio/mpeg": "mp3",
            "audio/mp4": "m4a",
            "audio/wav": "wav",
            "audio/webm": "webm",
            "audio/amr": "amr",
        }
        ext = ext_map.get(mime_type, "ogg")
        
        # كتابة الملف مؤقتاً
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        
        logger.info(f"[MEDIA] Transcribing audio ({len(audio_bytes)} bytes, {mime_type})")
        
        # إرسال لـ Whisper
        with open(tmp_path, "rb") as audio_file:
            transcript = _client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="ar",
                response_format="text"
            )
        
        # تنظيف الملف المؤقت
        import os
        os.unlink(tmp_path)
        
        text = transcript.strip() if isinstance(transcript, str) else str(transcript).strip()
        logger.info(f"[MEDIA] Transcription result: {text[:100]}")
        
        return text if text else None
        
    except Exception as e:
        logger.error(f"[MEDIA] Whisper transcription error: {e}", exc_info=True)
        # تنظيف الملف المؤقت في حالة الخطأ
        try:
            import os
            os.unlink(tmp_path)
        except Exception:
            pass
        return None


# ─── Formatting Results ─────────────────────────────────────────────────────

def format_image_analysis_response(analysis: Dict) -> str:
    """
    تنسيق نتيجة تحليل الصورة كرد للمستخدم
    """
    if not analysis:
        return "ما قدرت أتعرف على الصورة 😕 جرب صورة أوضح!"
    
    # إذا ليست منتج
    if analysis.get('is_product') is False:
        desc = analysis.get('description', 'صورة')
        return f"📸 شفت الصورة!\n{desc}\n\nإذا تبي تسألني عن منتج أو مكان، أرسل لي صورته! 🐺"
    
    product_ar = analysis.get('product_name_ar', 'منتج')
    category = analysis.get('category', '')
    description = analysis.get('description', '')
    
    response = f"📸 تعرفت على الصورة! 🐺\n\n"
    response += f"📦 *{product_ar}*\n"
    
    if description:
        response += f"📝 {description}\n"
    
    if category:
        response += f"\n🏪 تلقاه في: *{category}*\n"
    
    response += "\n⏳ جاري البحث عن أقرب مكان يبيعه في عنيزة..."
    
    return response
