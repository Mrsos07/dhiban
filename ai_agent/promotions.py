"""
نظام الترشيح الذكي للشركاء (Partner Promotion Engine)
────────────────────────────────────────────────────────
يقوم بترشيح الشركاء تلقائياً في المحادثات بطريقة ذكية وسياقية
بدون أن يطلب المستخدم ذلك، مع احترام:
  1. تطابق الفئة مع طلب المستخدم (لا نرشّح سباك لواحد طلب مطعم)
  2. cooldown زمني (لا نرشّح لنفس الشخص أكثر من مرة كل N دقيقة)
  3. تدوير (Rotation) — نفضّل الشركاء الأقل ظهوراً حديثاً
  4. عدم التكرار — لا نرشّح نفس الشريك لنفس المستخدم خلال فترة قصيرة
  5. عدم الحشو — لا نرشّح لو الرد الأصلي أصلاً يحتوي اسم الشريك
  6. تنوّع الأوقات — لا نبدأ كل محادثة بإعلان
"""
import logging
import random
import re
from datetime import timedelta
from typing import Optional, Dict, List

from django.db.models import Q, Count
from django.utils import timezone

logger = logging.getLogger(__name__)

# ─── إعدادات عامة ───
MIN_MINUTES_BETWEEN_PROMOS = 45      # لا يُرشَّح لنفس المستخدم إلا كل 45 دقيقة
MIN_MESSAGES_BETWEEN_PROMOS = 3      # لا يُرشَّح إلا بعد 3 رسائل من آخر ترشيح
SAME_PARTNER_COOLDOWN_DAYS = 3       # لا يُعرض نفس الشريك لنفس الشخص إلا بعد 3 أيام
MAX_PROMOS_PER_USER_PER_DAY = 3      # سقف ترشيحات اليومي لكل مستخدم
CHANCE_WHEN_ELIGIBLE = 0.75          # احتمالية حقن الترشيح حتى مع توفر كل الشروط (للتنوع)


# ─── خريطة الكلمات المفتاحية → الفئات (للكشف السياقي) ───
# نستخدم جذور كلمات لتغطية تصاريف عديدة
CONTEXT_KEYWORDS = {
    'مطعم': ['مطعم', 'مطاعم', 'اكل', 'أكل', 'غدا', 'غداء', 'عشا', 'عشاء', 'فطور',
             'مندي', 'كبسة', 'برقر', 'برجر', 'بيتزا', 'شاورما', 'بروست', 'جوعان'],
    'كافيه': ['كافيه', 'كوفي', 'قهوة', 'كفيه', 'مقهى', 'كافي', 'اسبريسو', 'لاتيه',
              'موكا', 'ستاربكس', 'حلا', 'حلى', 'دسرت'],
    'سباك': ['سباك', 'سباكة', 'مويه', 'طافحة', 'تسرب', 'حمام خرب', 'مغسلة'],
    'كهربائي': ['كهربائي', 'كهرباء', 'قاطع', 'تمديد', 'اسلاك', 'فيش'],
    'نجار': ['نجار', 'خشب', 'باب خرب', 'دولاب', 'نجارة'],
    'مكيف': ['مكيف', 'تكييف', 'فريون', 'سبليت', 'تنظيف مكيف'],
    'صيدلية': ['صيدلية', 'دواء', 'علاج', 'باراسيتامول', 'فيتامين'],
    'تنظيف': ['تنظيف', 'منظف', 'شركة تنظيف', 'تنضيف'],
    'صالون': ['حلاق', 'صالون', 'قص شعر', 'لحية'],
    'سوبرماركت': ['سوبرماركت', 'بقالة', 'تموينات'],
    'مغسلة': ['مغسلة', 'تنظيف ملابس', 'كوي'],
    'ورشة سيارات': ['ورشة', 'تصليح سيارة', 'ميكانيكي', 'كهرباء سيارات'],
    'تمشية': ['تمشية', 'اتمشى', 'نتمشى', 'خروجة', 'طلعة', 'كورنيش', 'حديقة', 'منتزه'],
}


def detect_context_category(user_message: str) -> Optional[str]:
    """
    يكشف الفئة المناسبة من رسالة المستخدم عبر مطابقة الكلمات المفتاحية.
    يرجع اسم الفئة (name_ar المُتوقَّع في Category) أو None.
    """
    if not user_message:
        return None
    text = user_message.lower()
    # إزالة التشكيل البسيط
    text = re.sub(r'[\u064B-\u0652]', '', text)

    best_match = None
    best_score = 0
    for category, keywords in CONTEXT_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > best_score:
            best_score = score
            best_match = category
    return best_match if best_score > 0 else None


def _is_cooldown_active(user_phone: str) -> bool:
    """تحقق من cooldown الزمني ورسائل — يرجع True إذا بدري على الترشيح."""
    from .models import PartnerPromotion

    if not user_phone:
        return True

    # cooldown زمني
    threshold = timezone.now() - timedelta(minutes=MIN_MINUTES_BETWEEN_PROMOS)
    last_promo = PartnerPromotion.objects.filter(
        user_phone=user_phone,
        created_at__gte=threshold,
    ).first()
    if last_promo:
        logger.debug(f"[PROMO] Cooldown active for {user_phone} (last: {last_promo.created_at})")
        return True

    # سقف يومي
    today = timezone.now() - timedelta(hours=24)
    daily_count = PartnerPromotion.objects.filter(
        user_phone=user_phone,
        created_at__gte=today,
    ).count()
    if daily_count >= MAX_PROMOS_PER_USER_PER_DAY:
        logger.debug(f"[PROMO] Daily cap reached for {user_phone} ({daily_count})")
        return True

    return False


def _messages_since_last_promo(user_phone: str) -> int:
    """يحسب كم رسالة مرّت منذ آخر ترشيح. يرجع رقم كبير إذا ما فيه ترشيح سابق."""
    from .models import PartnerPromotion
    try:
        from conversations.models import Conversation
        from users.models import WhatsAppUser

        last_promo = PartnerPromotion.objects.filter(user_phone=user_phone).first()
        if not last_promo:
            return 9999  # ما فيه ترشيحات سابقة

        user = WhatsAppUser.objects.filter(phone_number=user_phone).first()
        if not user:
            return 9999

        conv = Conversation.objects.filter(user=user).order_by('-started_at').first()
        if not conv or not conv.messages:
            return 9999

        count = 0
        for msg in reversed(conv.messages):
            ts = msg.get('timestamp')
            # احتساب كل رسالة user بعد آخر ترشيح
            if msg.get('role') == 'user':
                count += 1
            # إيقاف عند وصول تاريخ قبل الترشيح
            if ts and last_promo.created_at.isoformat() > ts:
                break
        return count
    except Exception as e:
        logger.debug(f"[PROMO] _messages_since_last_promo error: {e}")
        return 9999


def _pick_partner(category_name: str, user_phone: str) -> Optional[Dict]:
    """
    يختار شريكاً مناسباً للفئة مع تدوير (الأقل ظهوراً أولاً)
    ويتجنب الشركاء الذين شوهدوا مؤخراً من نفس المستخدم.
    """
    from suppliers.models import Supplier
    from .models import PartnerPromotion

    # شركاء من نفس الفئة (أو تحوي كلمة الفئة)
    qs = Supplier.objects.filter(is_partner=True, is_active=True).filter(
        Q(category__name_ar__icontains=category_name) |
        Q(category__name_en__icontains=category_name) |
        Q(subcategory__name_ar__icontains=category_name) |
        Q(services__icontains=category_name)
    )

    if not qs.exists():
        logger.debug(f"[PROMO] No partners found for category '{category_name}'")
        return None

    # استبعاد شركاء شاهدهم المستخدم خلال cooldown
    recent_cutoff = timezone.now() - timedelta(days=SAME_PARTNER_COOLDOWN_DAYS)
    recent_partner_ids = list(PartnerPromotion.objects.filter(
        user_phone=user_phone,
        created_at__gte=recent_cutoff,
    ).values_list('partner_id', flat=True))
    if recent_partner_ids:
        qs = qs.exclude(id__in=recent_partner_ids)

    if not qs.exists():
        logger.debug(f"[PROMO] All matching partners recently shown to {user_phone}")
        return None

    # ترتيب: الأعلى تقييماً أولاً، ثم عشوائية خفيفة بين أفضل 3
    top_partners = list(qs.order_by('-rating', '-reviews_count')[:3])
    chosen = random.choice(top_partners)

    return {
        'id': str(chosen.id),
        'obj': chosen,
        'name': chosen.name_ar,
        'rating': float(chosen.rating or 0),
        'phone': chosen.get_primary_phone() or '',
        'address': chosen.location.get('address', '') if isinstance(chosen.location, dict) else '',
        'notes': chosen.agent_notes or '',
        'maps_url': chosen.google_maps_url or '',
        'category': chosen.category.name_ar if chosen.category else category_name,
    }


def _format_promotion(partner: Dict) -> str:
    """صياغة رسالة الترشيح بأسلوب طبيعي دافئ — بدون إحساس إعلان مزعج."""
    templates = [
        "🤝 *وبالمناسبة يالغالي* — أنصحك بشريكنا المعتمد *{name}* في {category}، تقييمه {rating}/5 وناسه يمدحونه.",
        "💡 *فكرة* — لو تبي جربة ممتازة، شريكنا *{name}* ({category}) من أحسن اللي في عنيزة، ⭐ {rating}/5.",
        "✨ *بنصيحة صديق* — *{name}* شريك معتمد عندنا في {category}، تقييمه {rating}/5 وما يخيبك.",
        "🌟 *بالذمّة* — شريكنا *{name}* متميز في {category}، ⭐ {rating}/5. تستاهل تجربه.",
    ]
    base = random.choice(templates).format(
        name=partner['name'],
        category=partner['category'],
        rating=f"{partner['rating']:.1f}",
    )
    extras = []
    if partner.get('notes'):
        extras.append(f"📝 {partner['notes']}")
    if partner.get('phone'):
        extras.append(f"📞 {partner['phone']}")
    if partner.get('address'):
        extras.append(f"📍 {partner['address']}")
    if partner.get('maps_url'):
        extras.append(f"🗺️ الموقع:\n{partner['maps_url']}")

    if extras:
        base += "\n" + "\n".join(extras)
    return base


def _record_promotion(user_phone: str, partner_obj, category: str, user_message: str):
    """تسجيل الترشيح في قاعدة البيانات."""
    try:
        from .models import PartnerPromotion
        PartnerPromotion.objects.create(
            user_phone=user_phone,
            partner=partner_obj,
            context_keyword=category[:100],
            user_message=(user_message or '')[:500],
        )
    except Exception as e:
        logger.error(f"[PROMO] Failed to record promotion: {e}")


def maybe_promote(user_phone: str, user_message: str, agent_response: str) -> Optional[str]:
    """
    النقطة الرئيسية — تُستدعى بعد توليد رد الوكيل.
    ترجع نص الترشيح الذي يجب إلحاقه بالرد، أو None لو الشروط ما اكتملت.

    Args:
        user_phone: رقم جوال المستخدم (user_id)
        user_message: رسالة المستخدم الأخيرة
        agent_response: الرد الذي ولّده الوكيل (لنتأكد ما نكرر الشريك)

    Returns:
        نص الترشيح (يُضاف للرد) أو None
    """
    try:
        if not user_phone or not user_message:
            return None

        # 1) الكشف عن فئة سياقية
        category = detect_context_category(user_message)
        if not category:
            logger.debug("[PROMO] No context category detected")
            return None

        # 2) تحقق من cooldown
        if _is_cooldown_active(user_phone):
            return None

        # 3) تحقق من فاصل الرسائل
        msgs_since = _messages_since_last_promo(user_phone)
        if msgs_since < MIN_MESSAGES_BETWEEN_PROMOS:
            logger.debug(f"[PROMO] Only {msgs_since} messages since last promo")
            return None

        # 4) العشوائية للتنوع
        if random.random() > CHANCE_WHEN_ELIGIBLE:
            logger.debug("[PROMO] Skipped by random chance (diversity)")
            return None

        # 5) اختيار الشريك
        partner = _pick_partner(category, user_phone)
        if not partner:
            return None

        # 6) لا نكرّر لو الاسم موجود بالفعل في الرد
        if partner['name'] and partner['name'] in (agent_response or ''):
            logger.debug(f"[PROMO] Partner {partner['name']} already in response — skipping")
            return None

        # 7) بناء النص + التسجيل
        promo_text = _format_promotion(partner)
        _record_promotion(user_phone, partner['obj'], category, user_message)

        logger.info(f"[PROMO] Promoted '{partner['name']}' ({category}) to {user_phone}")
        return promo_text

    except Exception as e:
        logger.error(f"[PROMO] maybe_promote failed: {e}", exc_info=True)
        return None
