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
def _supplier_to_result_dict(partner, fallback_category: str = '') -> Dict:
    """تحويل كائن Supplier إلى dict متوافق مع تنسيق نتائج البحث."""
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
        'category': partner.category.name_ar if partner.category else fallback_category,
        'source': 'partner',
    }


def _score_partner(supplier, specific_terms: List[str], cat_tokens: List[str],
                   recent_promo_ids: Set[str]) -> Tuple[float, Dict]:
    """
    يحسب درجة ملاءمة الشريك للطلب. كل معيار يضيف نقاطاً موثّقة:
      • مطابقة specific_terms في الاسم = +100 (أقوى إشارة)
      • في الـ subcategory = +60
      • في agent_notes = +50 (ملاحظات يكتبها المدير لتوجيه الوكيل)
      • في services = +40
      • في description = +25
      • كل term إضافي مطابق يضاعف النقاط (جمع كلمات "مندي عوائل")
      • التقييم × 12 (0 → 60 نقطة لتقييم 5.0)
      • عدد المراجعات (مقيد): min(reviews, 300)/10 → 0-30 نقطة
      • رُشّح مؤخراً لنفس المستخدم (7 أيام): -1000 (تنويع قوي)
      • jitter عشوائي صغير ±3 لكسر التعادل الكامل
    """
    import random
    score = 0.0
    breakdown = {}

    name = (supplier.name_ar or '').lower()
    name_en = (supplier.name_en or '').lower()
    subcat = (supplier.subcategory.name_ar if getattr(supplier, 'subcategory_id', None) else '') or ''
    subcat_lower = subcat.lower()
    notes = (supplier.agent_notes or '').lower()
    services = (supplier.services or '').lower() if hasattr(supplier, 'services') else ''
    desc = (supplier.description or '').lower()

    # مطابقة المصطلحات المحددة
    term_hits = 0
    for term in specific_terms:
        t = term.lower().strip()
        if not t:
            continue
        matched_here = False
        if t in name or t in name_en:
            score += 100; matched_here = True
        if t in subcat_lower:
            score += 60; matched_here = True
        if t in notes:
            score += 50; matched_here = True
        if t in services:
            score += 40; matched_here = True
        if t in desc:
            score += 25; matched_here = True
        if matched_here:
            term_hits += 1
    breakdown['specific_match_pts'] = score
    breakdown['term_hits'] = term_hits

    # مكافأة مجاميع المصطلحات (لو أكثر من كلمة تطابق → "مندي عوائل" = إشارة قوية)
    if term_hits >= 2:
        score += 40
        breakdown['multi_term_bonus'] = 40

    # مطابقة الفئة العامة (أقل وزناً)
    cat_hits = 0
    for tok in cat_tokens:
        t = tok.lower().strip()
        if not t:
            continue
        cat_name = (supplier.category.name_ar if getattr(supplier, 'category_id', None) else '').lower()
        if t in cat_name or t in subcat_lower or t in services or t in desc:
            cat_hits += 1
    cat_pts = cat_hits * 15
    score += cat_pts
    breakdown['category_pts'] = cat_pts

    # التقييم + عدد المراجعات
    rating = float(supplier.rating or 0)
    reviews = int(supplier.reviews_count or 0)
    rating_pts = rating * 12
    review_pts = min(reviews, 300) / 10
    score += rating_pts + review_pts
    breakdown['rating_pts'] = round(rating_pts, 1)
    breakdown['review_pts'] = round(review_pts, 1)

    # عقوبة إذا رُشّح مؤخراً (تنويع قوي)
    if str(supplier.id) in recent_promo_ids:
        score -= 1000
        breakdown['recent_penalty'] = -1000

    # jitter لكسر التعادل
    jitter = random.uniform(-3, 3)
    score += jitter
    breakdown['jitter'] = round(jitter, 2)

    return score, breakdown


def find_best_partner(
    category: str,
    exclude_ids: Optional[set] = None,
    user_phone: Optional[str] = None,
    specific_terms: Optional[List[str]] = None,
) -> Optional[Dict]:
    """
    يختار **أفضل** شريك للطلب باستخدام نظام نقاط مرجّحة (_score_partner).
    يعالج تعدد الشركاء في القسم:
      • يرشّح الأقرب لسياق الطلب (مطابقة النوع في الاسم/التصنيف الفرعي/الخدمات)
      • يكافئ التقييم وعدد المراجعات
      • يعاقب التكرار لنفس المستخدم خلال 7 أيام
      • يحسم التعادل بـ jitter صغير لتنويع طفيف عبر الجلسات

    Args:
        category: الفئة الأساسية (مثلاً "مطعم")
        specific_terms: كلمات مفتاحية محددة من طلب المستخدم (مثلاً ["بروست"])
        exclude_ids: معرّفات شركاء يجب استبعادهم
        user_phone: لتطبيق عقوبة التكرار الحديث
    """
    if not category and not specific_terms:
        return None
    try:
        from suppliers.models import Supplier

        cat_tokens = [t.strip() for t in re.split(r'\s+', (category or '')) if len(t.strip()) >= 3]
        specific_terms = [t.strip() for t in (specific_terms or []) if t and len(t.strip()) >= 2]

        exclude_list: Set[str] = set(str(x) for x in (exclude_ids or []))

        # معرّفات الشركاء المرشّحين خلال آخر 7 أيام (لعقوبة، لا استبعاد كامل)
        recent_promo_ids: Set[str] = set()
        if user_phone:
            try:
                from .models import PartnerPromotion
                recent = PartnerPromotion.objects.filter(
                    user_phone=user_phone,
                    created_at__gte=datetime.utcnow() - timedelta(days=7),
                ).values_list('partner_id', flat=True)
                recent_promo_ids = {str(pid) for pid in recent}
            except Exception as e:
                logger.debug(f"[SEARCH-CTX] recent promo fetch failed: {e}")

        base_qs = Supplier.objects.filter(is_partner=True, is_active=True)
        if exclude_list:
            base_qs = base_qs.exclude(id__in=list(exclude_list))

        _generic_for_partner = {'مطعم', 'مطاعم', 'كافيه', 'كوفي', 'محل', 'متجر'}
        real_specific_terms = [t for t in specific_terms
                               if t.strip() not in _generic_for_partner]

        # ─── جمع مرشّحين: لا نلتقط إلا من يطابق النوع المحدد (ضمان عدم التضليل) ───
        candidates_qs = base_qs
        if real_specific_terms:
            specific_filter = Q()
            for term in real_specific_terms:
                specific_filter |= (
                    Q(name_ar__icontains=term) |
                    Q(name_en__icontains=term) |
                    Q(subcategory__name_ar__icontains=term) |
                    Q(services__icontains=term) |
                    Q(description__icontains=term) |
                    Q(agent_notes__icontains=term)
                )
            candidates_qs = candidates_qs.filter(specific_filter)
        elif cat_tokens:
            cat_filter = Q()
            for tok in cat_tokens:
                cat_filter |= (
                    Q(category__name_ar__icontains=tok) |
                    Q(category__name_en__icontains=tok) |
                    Q(subcategory__name_ar__icontains=tok) |
                    Q(services__icontains=tok) |
                    Q(description__icontains=tok)
                )
            candidates_qs = candidates_qs.filter(cat_filter)

        candidates = list(candidates_qs.distinct()[:30])  # pool موسّع للترجيح

        if not candidates:
            # لو طلب نوعاً محدداً ولم يوجد شريك مطابق → لا نحقن (تجنّب التضليل)
            if real_specific_terms:
                logger.info(f"[SEARCH-CTX] No partner matching specific terms {real_specific_terms} — "
                            f"skipping injection")
                return None
            # لو فئة عامة وكل الشركاء مُستبعدين، نتراخى ونعيد أي شريك بنفس الفئة
            relax_qs = Supplier.objects.filter(is_partner=True, is_active=True)
            if cat_tokens:
                rf = Q()
                for tok in cat_tokens:
                    rf |= (Q(category__name_ar__icontains=tok) |
                           Q(subcategory__name_ar__icontains=tok))
                relax_qs = relax_qs.filter(rf)
            candidates = list(relax_qs.distinct()[:20])
            if not candidates:
                return None
            logger.info(f"[SEARCH-CTX] Relaxed fallback: {len(candidates)} candidates")

        # ─── ترجيح وترتيب ───
        scored = [(sup, *_score_partner(sup, real_specific_terms, cat_tokens, recent_promo_ids))
                  for sup in candidates]
        scored.sort(key=lambda x: x[1], reverse=True)

        if not scored:
            return None

        best = scored[0]
        partner = best[0]
        logger.info(
            f"[SEARCH-CTX] Best partner: '{partner.name_ar}' score={best[1]:.1f} "
            f"breakdown={best[2]} | pool_size={len(scored)}"
        )
        # سجل أفضل 3 للمتابعة
        for i, (sup, sc, br) in enumerate(scored[:3]):
            logger.debug(f"[SEARCH-CTX]   #{i+1} {sup.name_ar}: {sc:.1f}")

        return _supplier_to_result_dict(partner, fallback_category=category)
    except Exception as e:
        logger.error(f"[SEARCH-CTX] find_best_partner error: {e}", exc_info=True)
        return None


# ─── Companion partner (cross-category suggestion) ─────────────────────────
# خريطة الفئات المترابطة: ما الفئات التي تُقترح بعد الفئة الحالية؟
# مثال: بعد العشاء → سوبرماركت أو كافيه أو حلويات
COMPANION_CATEGORIES: Dict[str, List[str]] = {
    'مطعم':       ['كافيه', 'حلويات', 'سوبرماركت', 'آيس كريم', 'مخبز'],
    'مطاعم':      ['كافيه', 'حلويات', 'سوبرماركت', 'آيس كريم', 'مخبز'],
    'كافيه':      ['حلويات', 'مخبز', 'مطعم', 'آيس كريم'],
    'كوفي':       ['حلويات', 'مخبز', 'مطعم', 'آيس كريم'],
    'حلويات':     ['كافيه', 'مطعم'],
    'آيس كريم':   ['كافيه', 'حلويات'],
    'مخبز':       ['كافيه', 'سوبرماركت'],
    'سوبرماركت':  ['مطعم', 'كافيه', 'مخبز'],
    'بقالة':      ['مطعم', 'كافيه'],
    'صيدلية':     ['سوبرماركت', 'مستشفى'],
    'صالون تجميل': ['كافيه', 'حلويات'],
    'حلاق':       ['كافيه', 'مطعم'],
    'صالة رياضية': ['كافيه', 'سوبرماركت'],
    'حديقة':      ['مطعم', 'كافيه', 'آيس كريم'],
}

# جمل وصل طبيعية حسب زوج (الفئة الحالية → فئة الرفيق)
# يستخدم {name} كـ placeholder لاسم الشريك
COMPANION_CONNECTORS: Dict[str, List[str]] = {
    # بعد المطعم
    ('مطعم', 'كافيه'): [
        "ولو حبيت كاسة قهوة بعد الأكل، أنصحك بـ *{name}* — جو مرتب وقهوته فخمة ☕",
        "وبعد الأكل، ترى *{name}* جلساتها حلوة لكوب قهوة يختم السهرة ☕",
    ],
    ('مطعم', 'سوبرماركت'): [
        "ولو تبي تدبّر شي قبل ترجع البيت، *{name}* جنب المنطقة وعندها كل شي تحتاجه 🛒",
        "وفي طريق عودتك لو تبي مشاوير البيت، *{name}* تلقى فيها كل اللي تحتاجه 🛒",
    ],
    ('مطعم', 'حلويات'): [
        "ولو تبي تحلّي بعد العشاء، *{name}* حلوياتها تجنن 🍰",
        "وللحلى بعد الأكل، *{name}* ما تندم — جرّب وادعي لي 🍰",
    ],
    ('مطعم', 'آيس كريم'): [
        "ولو تبي آيس كريم يكمّل السهرة، *{name}* اختيارنا الأول 🍦",
    ],
    ('مطعم', 'مخبز'): [
        "ولو تبي شي مع القهوة الصبح، *{name}* مخبوزاتها طازة 🥐",
    ],
    # بعد الكافيه
    ('كافيه', 'حلويات'): [
        "ولو تبي حلى يكمّل كوب القهوة، *{name}* اختيار ما يخيب 🍰",
    ],
    ('كافيه', 'مطعم'): [
        "ولو جاك جوع بعد القهوة، *{name}* جربّه وبتحب أكله 🍽️",
    ],
    ('كافيه', 'مخبز'): [
        "ولو تبي معجنات طازة مع قهوتك، *{name}* ما تقصّر 🥐",
    ],
    ('كافيه', 'آيس كريم'): [
        "ولو تبي تبرّد نفسك بعد القهوة، *{name}* آيس كريمه يوتي 🍦",
    ],
    # بعد السوبرماركت/البقالة
    ('سوبرماركت', 'مطعم'): [
        "ولو تبي تاكل قبل ما ترجع، *{name}* أكلها ممتاز 🍽️",
    ],
    ('سوبرماركت', 'كافيه'): [
        "ولو تبي استراحة قهوة بعد التسوّق، *{name}* جلساتها مرتبة ☕",
    ],
    # بعد الحلويات/الآيس كريم
    ('حلويات', 'كافيه'): [
        "ومع الحلى كوب قهوة يكمّل الطعم، *{name}* قهوتها تخبل ☕",
    ],
    ('آيس كريم', 'كافيه'): [
        "ولو تبي كوب قهوة يكمّل الجلسة، *{name}* اختيارنا المميز ☕",
    ],
    # الخدمات → ترفيه/غذاء
    ('صالون تجميل', 'كافيه'): [
        "ولما تخلصين، *{name}* جلساتها هادية لكاسة قهوة ☕",
    ],
    ('حلاق', 'كافيه'): [
        "ولما تخلص، *{name}* فيها جو حلو لكوب قهوة ☕",
    ],
    ('صالة رياضية', 'كافيه'): [
        "وبعد التمرين، *{name}* فيها مشروبات صحية ومكان هادي ☕",
    ],
    ('حديقة', 'مطعم'): [
        "ولما تخلصون من التمشية، *{name}* قريبة ومناسبة للعوائل 🍽️",
    ],
    ('حديقة', 'آيس كريم'): [
        "ومع جو الحديقة، آيس كريم من *{name}* يكمّل الأجواء 🍦",
    ],
}

# جملة افتراضية لأي زوج ما له اتصال مخصص
DEFAULT_COMPANION_CONNECTOR = "وبالمناسبة، لو احتجت شي من {cat}، *{name}* من الأسماء المميزة اللي نثق فيها."


def find_companion_partner(
    current_category: str,
    user_phone: Optional[str] = None,
    exclude_partner_id: Optional[str] = None,
) -> Optional[Dict]:
    """
    يختار شريكاً من فئة مرافقة (غير الفئة الحالية) لاقتراحه كإضافة طبيعية.
    مثال: بعد اقتراح مطعم → يقترح سوبرماركت/كافيه شريك.

    Args:
        current_category: الفئة التي بحث فيها المستخدم للتو (مثلاً "مطعم")
        user_phone: رقم المستخدم (لاستبعاد شركاء رُشّحوا مؤخراً)
        exclude_partner_id: معرّف شريك نريد استبعاده (عادةً الشريك الرئيسي المحقون)

    Returns:
        dict: {partner: dict, source_category: str, companion_category: str,
               connector_template: str} أو None
    """
    import random
    if not current_category:
        return None

    # استخراج الفئة الأساسية (الكلمة الأولى العربية)
    base_cat = None
    for key in COMPANION_CATEGORIES.keys():
        if key in current_category:
            base_cat = key
            break
    if not base_cat:
        return None

    companions = COMPANION_CATEGORIES.get(base_cat, [])
    if not companions:
        return None

    # نجرّب كل فئة مرافقة بترتيب عشوائي حتى نجد شريكاً متاحاً
    shuffled = companions.copy()
    random.shuffle(shuffled)

    for comp_cat in shuffled:
        partner_data = find_best_partner(
            category=comp_cat,
            exclude_ids={exclude_partner_id} if exclude_partner_id else None,
            user_phone=user_phone,
        )
        if partner_data:
            # اختيار جملة وصل مناسبة
            connectors = COMPANION_CONNECTORS.get((base_cat, comp_cat), [])
            if connectors:
                template = random.choice(connectors)
            else:
                template = DEFAULT_COMPANION_CONNECTOR
            return {
                'partner': partner_data,
                'source_category': base_cat,
                'companion_category': comp_cat,
                'connector_template': template,
            }

    return None


def format_companion_block(companion_data: Dict) -> str:
    """
    يبني بلوك المرافق كفقرة قصيرة طبيعية تلحق بالرد الرئيسي.
    يتضمن: الجملة الوصلية + رقم الهاتف + رابط الخريطة (اختصار).
    """
    partner = companion_data.get('partner') or {}
    template = companion_data.get('connector_template') or DEFAULT_COMPANION_CONNECTOR
    comp_cat = companion_data.get('companion_category', '')

    name = partner.get('name', '')
    try:
        sentence = template.format(name=name, cat=comp_cat)
    except Exception:
        sentence = f"*{name}* خيار مميز في {comp_cat}."

    lines = ["", sentence]
    if partner.get('phone'):
        lines.append(f"📞 {partner['phone']}")
    if partner.get('maps_url'):
        lines.append("🗺️ الموقع:")
        lines.append(partner['maps_url'])
    return "\n".join(lines)


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
