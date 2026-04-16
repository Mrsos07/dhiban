"""
إدارة سياق البحث الذكي للوكيل:
  1. كشف طلبات "البدائل" (غيرها / ثاني / بديل / ما عجبني ...)
  2. تتبّع الأسماء التي عُرضت سابقاً لكل مستخدم لكل فئة
  3. اختيار "الشريك الواحد المناسب" لحقنه في نتائج البحث

يعمل في الذاكرة فقط (per-process) — كافٍ للاستخدام على واتساب
حيث worker واحد يخدم كل الرسائل للمستخدم في سياق قصير.
"""
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple

from django.db.models import Q

logger = logging.getLogger(__name__)

# كلمات تدل على طلب بدائل/خيارات جديدة
ALT_KEYWORDS = [
    'غيرها', 'غيرهم', 'غيره', 'غير هذي', 'غير هذه',
    'ثاني', 'ثانية', 'ثانيه', 'ثواني',
    'بديل', 'بدائل', 'بديلة', 'بديله',
    'اقترح ثاني', 'اقترح لي ثاني', 'اقترح غير', 'اقترح لي غير',
    'ما عجبني', 'ما عجبتني', 'ماعجبني', 'ماعجبتني',
    'ما حبيت', 'ماحبيت', 'مو حلوة', 'مو حلو',
    'خيارات ثانية', 'خيارات اخرى', 'خيارات أخرى', 'خيارات جديدة',
    'زيادة', 'اكثر', 'أكثر', 'زيد', 'زودني',
    'تالي', 'التالي', 'اللي بعده', 'اللي بعدهم',
    'غير كذا', 'شي ثاني', 'شيء ثاني',
]


def is_alternatives_request(message: str) -> bool:
    """يكشف لو المستخدم يطلب بدائل لنتائج عُرضت سابقاً."""
    if not message:
        return False
    text = message.strip().lower()
    # إزالة التشكيل
    text = re.sub(r'[\u064B-\u0652]', '', text)
    return any(kw in text for kw in ALT_KEYWORDS)


# ─── Per-user search memory ─────────────────────────────────────────────────
# بنية: { user_id: { 'category': str, 'shown_names': set, 'timestamp': datetime } }
_MEMORY: Dict[str, Dict] = {}
_MEMORY_TTL = timedelta(minutes=30)  # النسيان بعد 30 دقيقة خمول


def _cleanup_expired():
    """حذف السجلات المنتهية."""
    now = datetime.utcnow()
    expired = [uid for uid, data in _MEMORY.items()
               if now - data.get('timestamp', now) > _MEMORY_TTL]
    for uid in expired:
        _MEMORY.pop(uid, None)


def get_context(user_id: str) -> Dict:
    """يرجع سياق البحث الحالي للمستخدم، أو dict فارغ."""
    _cleanup_expired()
    if not user_id:
        return {}
    return _MEMORY.get(user_id, {}).copy()


def record_search(user_id: str, category: str, shown_names: List[str]):
    """تسجيل نتائج بحث عُرضت للمستخدم."""
    if not user_id:
        return
    _cleanup_expired()
    existing = _MEMORY.get(user_id, {})
    # لو نفس الفئة، نضيف للأسماء المعروضة (تراكم)؛ لو فئة جديدة، نبدأ من جديد
    prev_cat = (existing.get('category') or '').strip().lower()
    if category and prev_cat == category.strip().lower():
        prev_shown: Set[str] = existing.get('shown_names') or set()
    else:
        prev_shown = set()
    new_shown = prev_shown | {n.strip() for n in shown_names if n}
    _MEMORY[user_id] = {
        'category': category or existing.get('category', ''),
        'shown_names': new_shown,
        'timestamp': datetime.utcnow(),
    }
    logger.info(f"[SEARCH-CTX] Recorded {len(new_shown)} shown names for {user_id} "
                f"(category={category})")


def get_exclusions(user_id: str) -> Set[str]:
    """يرجع الأسماء التي سبق عرضها للمستخدم في الفئة الحالية."""
    ctx = get_context(user_id)
    return ctx.get('shown_names') or set()


def clear_context(user_id: str):
    """مسح سياق البحث للمستخدم (مثلاً لما يبدأ موضوع جديد)."""
    if user_id:
        _MEMORY.pop(user_id, None)


# ─── Partner selection ─────────────────────────────────────────────────────
def find_best_partner(
    category: str,
    exclude_ids: Optional[set] = None,
    user_phone: Optional[str] = None,
) -> Optional[Dict]:
    """
    يختار "الشريك الواحد المناسب" للفئة الحالية.
    - is_partner=True
    - أعلى تقييم
    - مستبعد من exclude_ids (مثلاً شركاء ظهروا مؤخراً لنفس المستخدم)
    - يطابق على أي كلمة من الـ category (مثلاً "مطعم مندي" → يطابق category=مطعم)
    يرجع dict متوافق مع تنسيق نتائج البحث أو None.
    """
    if not category:
        return None
    try:
        from suppliers.models import Supplier
        # نقسّم category إلى كلمات ونبني OR filter على كل كلمة (≥3 حروف)
        tokens = [t.strip() for t in re.split(r'\s+', category) if len(t.strip()) >= 3]
        if not tokens:
            tokens = [category.strip()]

        match_filter = Q()
        for tok in tokens:
            match_filter |= (
                Q(category__name_ar__icontains=tok) |
                Q(category__name_en__icontains=tok) |
                Q(subcategory__name_ar__icontains=tok) |
                Q(services__icontains=tok) |
                Q(description__icontains=tok)
            )
        qs = Supplier.objects.filter(is_partner=True, is_active=True).filter(match_filter)
        if exclude_ids:
            qs = qs.exclude(id__in=list(exclude_ids))

        # استبعاد الشركاء الذين رُشّحوا لهذا المستخدم خلال 24 ساعة
        if user_phone:
            try:
                from .models import PartnerPromotion
                recent = PartnerPromotion.objects.filter(
                    user_phone=user_phone,
                    created_at__gte=datetime.utcnow() - timedelta(hours=24),
                ).values_list('partner_id', flat=True)
                if recent:
                    qs = qs.exclude(id__in=list(recent))
            except Exception as e:
                logger.debug(f"[SEARCH-CTX] promotion exclude failed: {e}")

        partner = qs.order_by('-rating', '-reviews_count').first()
        if not partner:
            return None

        # بناء dict مطابق لتنسيق search results (لتمريره مباشرة للـ formatter)
        loc = partner.location if isinstance(partner.location, dict) else {}
        maps_url = partner.google_maps_url or ''
        if not maps_url and loc.get('lat') and loc.get('lng'):
            maps_url = f"https://www.google.com/maps/search/?api=1&query={loc['lat']},{loc['lng']}"

        return {
            '_partner_id': str(partner.id),
            'name': partner.name_ar,
            'rating': float(partner.rating or 0),
            'total_ratings': int(partner.reviews_count or 0),
            'address': loc.get('address', ''),
            'location': loc,
            'phone': partner.get_primary_phone() or '',
            'maps_url': maps_url,
            'is_partner': True,
            'agent_notes': partner.agent_notes or '',
            'category': partner.category.name_ar if partner.category else category,
            'source': 'partner',
        }
    except Exception as e:
        logger.error(f"[SEARCH-CTX] find_best_partner error: {e}", exc_info=True)
        return None


def record_partner_promotion(user_phone: str, partner_id: str, category: str, user_message: str):
    """تسجيل ترشيح الشريك (يستخدم نفس جدول PartnerPromotion للمنع/الإحصاء)."""
    if not user_phone or not partner_id:
        return
    try:
        from .models import PartnerPromotion
        from suppliers.models import Supplier
        partner = Supplier.objects.filter(id=partner_id).first()
        if not partner:
            return
        PartnerPromotion.objects.create(
            user_phone=user_phone,
            partner=partner,
            context_keyword=(category or '')[:100],
            user_message=(user_message or '')[:500],
        )
    except Exception as e:
        logger.error(f"[SEARCH-CTX] record_partner_promotion failed: {e}")
