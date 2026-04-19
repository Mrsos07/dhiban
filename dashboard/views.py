import csv
import json
from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.db.models import Count, Q
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
import os

from users.models import WhatsAppUser
from suppliers.models import Supplier, Category, SubCategory
from conversations.models import Conversation
from service_requests.models import ServiceRequest
from ai_agent.models import AgentSettings


@staff_member_required
def dashboard_index(request):
    """الصفحة الرئيسية للوحة التحكم"""
    today = timezone.now().date()
    week_ago = today - timedelta(days=7)
    
    stats = {
        'users_count': WhatsAppUser.objects.count(),
        'users_today': WhatsAppUser.objects.filter(registration_date__date=today).count(),
        'suppliers_count': Supplier.objects.count(),
        'partners_count': Supplier.objects.filter(is_partner=True).count(),
        'conversations_count': Conversation.objects.count(),
        'active_conversations': Conversation.objects.filter(ended_at__isnull=True).count(),
        'requests_count': ServiceRequest.objects.count(),
        'completed_requests': ServiceRequest.objects.filter(status='completed').count(),
    }
    
    recent_users = WhatsAppUser.objects.order_by('-registration_date')[:5]
    recent_suppliers = Supplier.objects.select_related('category').order_by('-created_at')[:5]
    
    chart_labels = []
    chart_conversations = []
    chart_requests = []
    
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        chart_labels.append(day.strftime('%m/%d'))
        chart_conversations.append(Conversation.objects.filter(started_at__date=day).count())
        chart_requests.append(ServiceRequest.objects.filter(timestamp__date=day).count())
    
    # حالة Evolution API
    try:
        from whatsapp.evolution_api import evolution_api
        from django.conf import settings as django_settings
        evolution_configured = bool(
            getattr(django_settings, 'EVOLUTION_API_URL', '') and
            getattr(django_settings, 'EVOLUTION_API_KEY', '')
        )
        whatsapp_connected = evolution_api.is_connected() if evolution_configured else False
    except Exception:
        evolution_configured = False
        whatsapp_connected = False

    context = {
        'stats': stats,
        'recent_users': recent_users,
        'recent_suppliers': recent_suppliers,
        'chart_labels': json.dumps(chart_labels),
        'chart_conversations': json.dumps(chart_conversations),
        'chart_requests': json.dumps(chart_requests),
        'evolution_configured': evolution_configured,
        'whatsapp_connected': whatsapp_connected,
    }
    return render(request, 'dashboard/index.html', context)


@staff_member_required
def suppliers_list(request):
    """قائمة الموردين"""
    suppliers = Supplier.objects.select_related('category', 'subcategory').all()
    categories = Category.objects.filter(is_active=True).order_by('order', 'name_ar')
    
    q = request.GET.get('q', '')
    category = request.GET.get('category', '')
    status = request.GET.get('status', '')
    min_rating = request.GET.get('min_rating', '')
    max_rating = request.GET.get('max_rating', '')
    sort_by = request.GET.get('sort', '-rating')
    
    if q:
        suppliers = suppliers.filter(Q(name_ar__icontains=q) | Q(name_en__icontains=q))
    if category:
        suppliers = suppliers.filter(category_id=category)
    if status == 'active':
        suppliers = suppliers.filter(is_active=True)
    elif status == 'partner':
        suppliers = suppliers.filter(is_partner=True)
    elif status == 'inactive':
        suppliers = suppliers.filter(is_active=False)
    
    # فلتر التقييم
    if min_rating:
        try:
            suppliers = suppliers.filter(rating__gte=float(min_rating))
        except ValueError:
            pass
    if max_rating:
        try:
            suppliers = suppliers.filter(rating__lte=float(max_rating))
        except ValueError:
            pass
    
    # الترتيب
    valid_sorts = ['rating', '-rating', 'name_ar', '-name_ar', 'created_at', '-created_at', 'reviews_count', '-reviews_count']
    if sort_by in valid_sorts:
        suppliers = suppliers.order_by(sort_by)
    else:
        suppliers = suppliers.order_by('-rating')
    
    return render(request, 'dashboard/suppliers_list.html', {
        'suppliers': suppliers,
        'categories': categories,
        'current_category': category,
        'current_status': status,
        'current_min_rating': min_rating,
        'current_max_rating': max_rating,
        'current_sort': sort_by,
        'current_q': q,
    })


@staff_member_required
def supplier_add(request):
    """إضافة مورد جديد"""
    categories = Category.objects.filter(is_active=True)
    subcategories = SubCategory.objects.filter(is_active=True)
    
    if request.method == 'POST':
        supplier = Supplier.objects.create(
            name_ar=request.POST.get('name_ar'),
            name_en=request.POST.get('name_en', ''),
            description=request.POST.get('description', ''),
            category_id=request.POST.get('category'),
            subcategory_id=request.POST.get('subcategory') or None,
            email=request.POST.get('email', ''),
            website=request.POST.get('website', ''),
            google_maps_place_id=request.POST.get('google_maps_place_id', ''),
            phone_numbers=[request.POST.get('phone')] if request.POST.get('phone') else [],
            location={
                'lat': float(request.POST.get('lat') or 0),
                'lng': float(request.POST.get('lng') or 0),
                'address': request.POST.get('address', '')
            },
            is_partner='is_partner' in request.POST,
            is_verified='is_verified' in request.POST,
            is_active='is_active' in request.POST,
        )
        messages.success(request, f'تم إضافة المورد "{supplier.name_ar}" بنجاح.')
        return redirect('dashboard:suppliers_list')
    
    return render(request, 'dashboard/supplier_form.html', {
        'categories': categories,
        'subcategories': subcategories,
    })


@staff_member_required
def supplier_edit(request, pk):
    """تعديل مورد"""
    supplier = get_object_or_404(Supplier, pk=pk)
    categories = Category.objects.filter(is_active=True)
    subcategories = SubCategory.objects.filter(is_active=True)
    
    if request.method == 'POST':
        supplier.name_ar = request.POST.get('name_ar')
        supplier.name_en = request.POST.get('name_en', '')
        supplier.description = request.POST.get('description', '')
        supplier.category_id = request.POST.get('category')
        supplier.subcategory_id = request.POST.get('subcategory') or None
        supplier.email = request.POST.get('email', '')
        supplier.website = request.POST.get('website', '')
        supplier.google_maps_place_id = request.POST.get('google_maps_place_id', '')
        supplier.phone_numbers = [request.POST.get('phone')] if request.POST.get('phone') else []
        supplier.location = {
            'lat': float(request.POST.get('lat') or 0),
            'lng': float(request.POST.get('lng') or 0),
            'address': request.POST.get('address', '')
        }
        supplier.is_partner = 'is_partner' in request.POST
        supplier.is_verified = 'is_verified' in request.POST
        supplier.is_active = 'is_active' in request.POST
        supplier.save()
        messages.success(request, f'تم تحديث المورد "{supplier.name_ar}" بنجاح.')
        return redirect('dashboard:suppliers_list')
    
    return render(request, 'dashboard/supplier_form.html', {
        'supplier': supplier,
        'categories': categories,
        'subcategories': subcategories,
    })


@staff_member_required
def supplier_delete(request, pk):
    """حذف مورد"""
    supplier = get_object_or_404(Supplier, pk=pk)
    name = supplier.name_ar
    supplier.delete()
    messages.success(request, f'تم حذف المورد "{name}" بنجاح.')
    return redirect('dashboard:suppliers_list')


@staff_member_required
def partners_list(request):
    """قائمة الشركاء المعتمدين"""
    partners = Supplier.objects.select_related('category', 'subcategory').filter(is_partner=True)
    categories = Category.objects.filter(is_active=True).order_by('order', 'name_ar')

    q = request.GET.get('q', '')
    category = request.GET.get('category', '')
    status = request.GET.get('status', '')

    if q:
        partners = partners.filter(Q(name_ar__icontains=q) | Q(name_en__icontains=q) | Q(description__icontains=q))
    if category:
        partners = partners.filter(category_id=category)
    if status == 'active':
        partners = partners.filter(is_active=True)
    elif status == 'inactive':
        partners = partners.filter(is_active=False)

    partners = partners.order_by('-rating', 'name_ar')

    return render(request, 'dashboard/partners_list.html', {
        'partners': partners,
        'categories': categories,
        'current_q': q,
        'current_category': category,
        'current_status': status,
    })


@staff_member_required
def partner_add(request):
    """إضافة شريك جديد"""
    categories = Category.objects.filter(is_active=True).order_by('order', 'name_ar')
    subcategories = SubCategory.objects.filter(is_active=True).select_related('category')

    if request.method == 'POST':
        phone = request.POST.get('phone', '').strip()
        lat = request.POST.get('lat', '').strip()
        lng = request.POST.get('lng', '').strip()
        partner = Supplier.objects.create(
            name_ar=request.POST.get('name_ar', '').strip(),
            name_en=request.POST.get('name_en', '').strip(),
            description=request.POST.get('description', '').strip(),
            agent_notes=request.POST.get('agent_notes', '').strip(),
            category_id=request.POST.get('category'),
            subcategory_id=request.POST.get('subcategory') or None,
            email=request.POST.get('email', '').strip(),
            website=request.POST.get('website', '').strip(),
            google_maps_url=request.POST.get('google_maps_url', '').strip(),
            google_maps_place_id=request.POST.get('google_maps_place_id', '').strip(),
            phone_numbers=[phone] if phone else [],
            rating=float(request.POST.get('rating') or 0),
            reviews_count=int(request.POST.get('reviews_count') or 0),
            location={
                'lat': float(lat) if lat else 0,
                'lng': float(lng) if lng else 0,
                'address': request.POST.get('address', '').strip(),
            },
            is_partner=True,
            is_verified='is_verified' in request.POST,
            is_active='is_active' in request.POST,
        )
        messages.success(request, f'تم إضافة الشريك "{partner.name_ar}" بنجاح.')
        return redirect('dashboard:partners_list')

    return render(request, 'dashboard/partner_form.html', {
        'categories': categories,
        'subcategories': subcategories,
    })


@staff_member_required
def partner_edit(request, pk):
    """تعديل شريك"""
    partner = get_object_or_404(Supplier, pk=pk, is_partner=True)
    categories = Category.objects.filter(is_active=True).order_by('order', 'name_ar')
    subcategories = SubCategory.objects.filter(is_active=True).select_related('category')

    if request.method == 'POST':
        phone = request.POST.get('phone', '').strip()
        lat = request.POST.get('lat', '').strip()
        lng = request.POST.get('lng', '').strip()
        partner.name_ar = request.POST.get('name_ar', '').strip()
        partner.name_en = request.POST.get('name_en', '').strip()
        partner.description = request.POST.get('description', '').strip()
        partner.agent_notes = request.POST.get('agent_notes', '').strip()
        partner.category_id = request.POST.get('category')
        partner.subcategory_id = request.POST.get('subcategory') or None
        partner.email = request.POST.get('email', '').strip()
        partner.website = request.POST.get('website', '').strip()
        partner.google_maps_url = request.POST.get('google_maps_url', '').strip()
        partner.google_maps_place_id = request.POST.get('google_maps_place_id', '').strip()
        partner.phone_numbers = [phone] if phone else []
        partner.rating = float(request.POST.get('rating') or 0)
        partner.reviews_count = int(request.POST.get('reviews_count') or 0)
        partner.location = {
            'lat': float(lat) if lat else 0,
            'lng': float(lng) if lng else 0,
            'address': request.POST.get('address', '').strip(),
        }
        partner.is_partner = True
        partner.is_verified = 'is_verified' in request.POST
        partner.is_active = 'is_active' in request.POST
        partner.save()
        messages.success(request, f'تم تحديث الشريك "{partner.name_ar}" بنجاح.')
        return redirect('dashboard:partners_list')

    return render(request, 'dashboard/partner_form.html', {
        'partner': partner,
        'categories': categories,
        'subcategories': subcategories,
    })


@staff_member_required
def partner_delete(request, pk):
    """حذف شريك"""
    partner = get_object_or_404(Supplier, pk=pk, is_partner=True)
    if request.method == 'POST':
        name = partner.name_ar
        partner.delete()
        messages.success(request, f'تم حذف الشريك "{name}" بنجاح.')
        return redirect('dashboard:partners_list')
    return render(request, 'dashboard/partner_confirm_delete.html', {'partner': partner})


def get_subcategories_api(request):
    """API لجلب التصنيفات الفرعية حسب التصنيف الرئيسي"""
    category_id = request.GET.get('category_id', '')
    subs = SubCategory.objects.filter(is_active=True)
    if category_id:
        subs = subs.filter(category_id=category_id)
    data = [{'id': str(s.id), 'name': s.name_ar} for s in subs.order_by('name_ar')]
    return JsonResponse({'subcategories': data})


@staff_member_required
def users_list(request):
    """قائمة المستهلكين"""
    users = WhatsAppUser.objects.all()
    
    q = request.GET.get('q', '')
    status = request.GET.get('status', '')
    
    if q:
        users = users.filter(Q(name__icontains=q) | Q(phone_number__icontains=q))
    if status == 'active':
        users = users.filter(is_active=True)
    elif status == 'inactive':
        users = users.filter(is_active=False)
    
    return render(request, 'dashboard/users_list.html', {'users': users})


@staff_member_required
def user_detail(request, pk):
    """تفاصيل مستهلك"""
    user = get_object_or_404(WhatsAppUser, pk=pk)
    conversations = user.conversations.all()[:10]
    return render(request, 'dashboard/user_detail.html', {
        'whatsapp_user': user,
        'conversations': conversations,
    })


@staff_member_required
def conversations_list(request):
    """قائمة المحادثات"""
    conversations = Conversation.objects.select_related('user').all()
    
    q = request.GET.get('q', '')
    intent = request.GET.get('intent', '')
    status = request.GET.get('status', '')
    
    if q:
        conversations = conversations.filter(user__phone_number__icontains=q)
    if intent:
        conversations = conversations.filter(intent_detected=intent)
    if status == 'resolved':
        conversations = conversations.filter(resolved=True)
    elif status == 'pending':
        conversations = conversations.filter(resolved=False)
    
    return render(request, 'dashboard/conversations_list.html', {'conversations': conversations})


@staff_member_required
def conversation_detail(request, pk):
    """تفاصيل محادثة"""
    conversation = get_object_or_404(Conversation, pk=pk)
    return render(request, 'dashboard/conversation_detail.html', {'conversation': conversation})


@staff_member_required
def categories_list(request):
    """قائمة التصنيفات مع التصنيفات الفرعية المنضوية تحتها"""
    categories = (
        Category.objects
        .annotate(suppliers_count=Count('suppliers'))
        .prefetch_related('subcategories')
        .order_by('order', 'name_ar')
    )
    return render(request, 'dashboard/categories_list.html', {'categories': categories})


@staff_member_required
def category_add(request):
    """إضافة تصنيف رئيسي"""
    if request.method == 'POST':
        name_ar = (request.POST.get('name_ar') or '').strip()
        if not name_ar:
            messages.error(request, 'الاسم بالعربية مطلوب.')
            return redirect('dashboard:categories_list')
        Category.objects.create(
            name_ar=name_ar,
            name_en=(request.POST.get('name_en') or '').strip(),
            icon=(request.POST.get('icon') or 'folder').strip(),
        )
        messages.success(request, f'تم إضافة التصنيف "{name_ar}" بنجاح.')
    return redirect('dashboard:categories_list')


@staff_member_required
@require_http_methods(["POST"])
def category_edit(request, pk):
    """تعديل تصنيف رئيسي"""
    cat = get_object_or_404(Category, pk=pk)
    cat.name_ar = (request.POST.get('name_ar') or cat.name_ar).strip()
    cat.name_en = (request.POST.get('name_en') or '').strip()
    cat.icon = (request.POST.get('icon') or cat.icon or 'folder').strip()
    cat.is_active = request.POST.get('is_active') == 'on'
    cat.save()
    messages.success(request, f'تم تحديث التصنيف "{cat.name_ar}".')
    return redirect('dashboard:categories_list')


@staff_member_required
@require_http_methods(["POST"])
def category_delete(request, pk):
    """حذف تصنيف رئيسي (يحذف التصنيفات الفرعية تلقائياً)"""
    cat = get_object_or_404(Category, pk=pk)
    if cat.suppliers.exists():
        messages.error(
            request,
            f'لا يمكن حذف "{cat.name_ar}" لأنه مرتبط بـ {cat.suppliers.count()} مورد. '
            'انقل الموردين لتصنيف آخر أولاً أو أوقف التصنيف بدلاً من حذفه.',
        )
        return redirect('dashboard:categories_list')
    name = cat.name_ar
    cat.delete()
    messages.success(request, f'تم حذف التصنيف "{name}".')
    return redirect('dashboard:categories_list')


# ─── التصنيفات الفرعية ────────────────────────────────────────────────

@staff_member_required
@require_http_methods(["POST"])
def subcategory_add(request):
    """إضافة تصنيف فرعي داخل تصنيف رئيسي"""
    category_id = request.POST.get('category_id')
    name_ar = (request.POST.get('name_ar') or '').strip()
    if not (category_id and name_ar):
        messages.error(request, 'التصنيف الرئيسي والاسم بالعربية مطلوبان.')
        return redirect('dashboard:categories_list')
    parent = get_object_or_404(Category, pk=category_id)
    # تجنّب التكرار (unique_together في النموذج)
    if SubCategory.objects.filter(category=parent, name_ar=name_ar).exists():
        messages.warning(request, f'"{name_ar}" موجود مسبقاً تحت "{parent.name_ar}".')
        return redirect('dashboard:categories_list')
    SubCategory.objects.create(
        category=parent,
        name_ar=name_ar,
        name_en=(request.POST.get('name_en') or '').strip(),
        is_active=True,
    )
    messages.success(request, f'تم إضافة "{name_ar}" تحت "{parent.name_ar}".')
    return redirect('dashboard:categories_list')


@staff_member_required
@require_http_methods(["POST"])
def subcategory_edit(request, pk):
    """تعديل تصنيف فرعي"""
    sub = get_object_or_404(SubCategory, pk=pk)
    new_name = (request.POST.get('name_ar') or sub.name_ar).strip()
    # فحص التكرار قبل التحديث
    if new_name != sub.name_ar and SubCategory.objects.filter(
        category=sub.category, name_ar=new_name
    ).exclude(pk=sub.pk).exists():
        messages.warning(request, f'"{new_name}" موجود مسبقاً تحت "{sub.category.name_ar}".')
        return redirect('dashboard:categories_list')
    sub.name_ar = new_name
    sub.name_en = (request.POST.get('name_en') or '').strip()
    sub.is_active = request.POST.get('is_active') == 'on'
    sub.save()
    messages.success(request, f'تم تحديث التصنيف الفرعي "{sub.name_ar}".')
    return redirect('dashboard:categories_list')


@staff_member_required
@require_http_methods(["POST"])
def subcategory_delete(request, pk):
    """حذف تصنيف فرعي"""
    sub = get_object_or_404(SubCategory, pk=pk)
    linked = Supplier.objects.filter(subcategory=sub).count()
    if linked:
        messages.error(
            request,
            f'لا يمكن حذف "{sub.name_ar}" لأنه مرتبط بـ {linked} مورد. '
            'غيّر تصنيف الموردين أولاً.',
        )
        return redirect('dashboard:categories_list')
    name = sub.name_ar
    parent_name = sub.category.name_ar
    sub.delete()
    messages.success(request, f'تم حذف "{name}" من تحت "{parent_name}".')
    return redirect('dashboard:categories_list')


@staff_member_required
def export_data(request):
    """صفحة تصدير البيانات"""
    return render(request, 'dashboard/export_data.html')


@staff_member_required
def export_users(request):
    """تصدير المستهلكين CSV"""
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = 'attachment; filename="users.csv"'
    response.write('\ufeff')
    
    writer = csv.writer(response)
    writer.writerow(['الاسم', 'رقم الهاتف', 'معرف واتساب', 'تاريخ التسجيل', 'آخر تفاعل', 'الحالة'])
    
    for user in WhatsAppUser.objects.all():
        writer.writerow([
            user.name or '',
            user.phone_number,
            user.whatsapp_id,
            user.registration_date.strftime('%Y-%m-%d %H:%M'),
            user.last_interaction.strftime('%Y-%m-%d %H:%M'),
            'نشط' if user.is_active else 'غير نشط'
        ])
    
    return response


@staff_member_required
def export_suppliers(request):
    """تصدير الموردين CSV"""
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = 'attachment; filename="suppliers.csv"'
    response.write('\ufeff')
    
    writer = csv.writer(response)
    writer.writerow(['الاسم', 'التصنيف', 'الهاتف', 'البريد', 'التقييم', 'شريك', 'الحالة'])
    
    for s in Supplier.objects.select_related('category').all():
        writer.writerow([
            s.name_ar,
            s.category.name_ar if s.category else '',
            s.get_primary_phone() or '',
            s.email,
            s.rating,
            'نعم' if s.is_partner else 'لا',
            'نشط' if s.is_active else 'غير نشط'
        ])
    
    return response


@staff_member_required
def export_conversations(request):
    """تصدير المحادثات CSV"""
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = 'attachment; filename="conversations.csv"'
    response.write('\ufeff')
    
    writer = csv.writer(response)
    writer.writerow(['المستخدم', 'النوع', 'عدد الرسائل', 'البداية', 'النهاية', 'الحالة'])
    
    for c in Conversation.objects.select_related('user').all():
        writer.writerow([
            c.user.phone_number,
            c.get_intent_detected_display(),
            c.get_messages_count(),
            c.started_at.strftime('%Y-%m-%d %H:%M'),
            c.ended_at.strftime('%Y-%m-%d %H:%M') if c.ended_at else '',
            'تم الحل' if c.resolved else 'قيد الانتظار'
        ])
    
    return response


# ========== Agent Views ==========

@staff_member_required
def agent_test(request):
    """صفحة تجربة الوكيل"""
    settings = AgentSettings.get_active()
    if not settings:
        settings = AgentSettings.objects.create()
    
    return render(request, 'dashboard/agent_test.html', {
        'settings': settings,
        'welcome_message': settings.welcome_message,
        'api_configured': bool(os.environ.get('OPENAI_API_KEY')),
    })


@staff_member_required
@require_http_methods(['POST'])
def agent_chat(request):
    """API لمحادثة الوكيل"""
    try:
        data = json.loads(request.body)
        
        # مسح الذاكرة إذا طُلب ذلك
        if data.get('clear_history'):
            request.session['agent_chat_history'] = []
            request.session.modified = True
            return JsonResponse({'status': 'cleared'})
        
        message = data.get('message', '')
        if not message:
            return JsonResponse({'error': 'الرسالة مطلوبة'}, status=400)
        
        from ai_agent.agent import dhiban_agent
        
        # استخدام التاريخ المُمرَّر من الـ JavaScript مباشرة
        chat_history = data.get('history', [])
        
        # معالجة الرسالة مع التاريخ
        response = dhiban_agent.process_message_with_history(message, chat_history, user_id=data.get('user_id'))
        
        # دعم تعدد الرسائل: الوكيل قد يرجع list (رسالة رئيسية + رسالة شريك مستقلة)
        if isinstance(response, list):
            # للواجهة: نرجع كلا الرسالتين حتى تعرضهما بشكل منفصل
            return JsonResponse({
                'response': response[0] if response else '',
                'messages': response,  # الواجهة الجديدة تقرأ هذا
            })
        return JsonResponse({'response': response, 'messages': [response]})
    
    except Exception as e:
        return JsonResponse({'error': str(e), 'response': 'حدث خطأ في معالجة الرسالة.'}, status=500)


@staff_member_required
def whatsapp_connect(request):
    """صفحة ربط واتساب عبر Evolution API"""
    from whatsapp.evolution_api import evolution_api
    from django.conf import settings as django_settings

    evolution_configured = bool(
        getattr(django_settings, 'EVOLUTION_API_URL', '') and
        getattr(django_settings, 'EVOLUTION_API_KEY', '')
    )

    connected = False
    qr_base64 = None
    instance_state = 'unknown'

    if evolution_configured:
        # جلب حالة الاتصال مع دعم كلا الصيغتين
        status_result = evolution_api.get_instance_status()
        if status_result.get('success'):
            data = status_result['data']
            state = data.get('instance', {}).get('state', '') or data.get('state', '')
            instance_state = state or 'unknown'
            connected = (state == 'open')

        if not connected:
            # استخدام get_or_create_qrcode الذكية
            qr_base64 = evolution_api.get_or_create_qrcode()

    webhook_url = getattr(django_settings, 'EVOLUTION_WEBHOOK_URL', '')
    instance_name = getattr(django_settings, 'EVOLUTION_INSTANCE_NAME', 'dhiban')

    return render(request, 'dashboard/whatsapp_connect.html', {
        'evolution_configured': evolution_configured,
        'connected': connected,
        'instance_state': instance_state,
        'qr_base64': qr_base64,
        'webhook_url': webhook_url,
        'instance_name': instance_name,
    })


@staff_member_required
@require_http_methods(['POST'])
def whatsapp_disconnect(request):
    """قطع اتصال الواتساب — مع معالجة ذكية لأخطاء Evolution API"""
    from whatsapp.evolution_api import evolution_api
    result = evolution_api.logout_instance()

    if result.get('success'):
        data = result.get('data') or {}
        if isinstance(data, dict) and data.get('message') == 'instance already disconnected':
            messages.info(request, 'الـ instance كان غير متصل أصلاً — تم تأكيد قطع الاتصال.')
        else:
            messages.success(request, 'تم قطع اتصال الواتساب بنجاح.')
        return redirect('dashboard:whatsapp_connect')

    # فشل فعلي — نوضح السبب
    status = result.get('status')
    err = result.get('error', 'خطأ غير معروف')
    if status == 500:
        messages.error(
            request,
            'Evolution API أرجع خطأ داخلي (500). غالباً الـ instance في حالة غير طبيعية. '
            'جرّب إعادة تشغيل الـ instance أو حذفه وإعادة إنشائه.'
        )
    elif status == 404:
        messages.warning(request, 'الـ instance غير موجود على Evolution API — لا شيء لقطعه.')
    else:
        messages.error(request, f"فشل قطع الاتصال: {err}")
    return redirect('dashboard:whatsapp_connect')


@staff_member_required
def whatsapp_status_api(request):
    """API لجلب حالة الاتصال وQR Code (تُستخدم بـ AJAX)"""
    from whatsapp.evolution_api import evolution_api
    from django.conf import settings as django_settings

    evolution_configured = bool(
        getattr(django_settings, 'EVOLUTION_API_URL', '') and
        getattr(django_settings, 'EVOLUTION_API_KEY', '')
    )

    if not evolution_configured:
        return JsonResponse({'connected': False, 'state': 'not_configured', 'qr': None})

    status_result = evolution_api.get_instance_status()
    state = 'unknown'
    connected = False

    if status_result.get('success'):
        data = status_result['data']
        state = data.get('instance', {}).get('state', '') or data.get('state', 'unknown')
        connected = (state == 'open')

    qr_base64 = None
    if not connected:
        # جلب QR مع دعم جميع الصيغ
        qr_result = evolution_api.get_qrcode()
        if qr_result.get('success'):
            qr_base64 = evolution_api.extract_qr_base64(qr_result['data'])

    return JsonResponse({'connected': connected, 'state': state, 'qr': qr_base64})


@staff_member_required
def whatsapp_set_webhook(request):
    """تعيين webhook URL لـ Evolution API"""
    from whatsapp.evolution_api import evolution_api
    from django.conf import settings as django_settings

    webhook_url = getattr(django_settings, 'EVOLUTION_WEBHOOK_URL', '')
    if not webhook_url:
        messages.error(request, 'EVOLUTION_WEBHOOK_URL غير محدد في الإعدادات.')
        return redirect('dashboard:whatsapp_connect')

    result = evolution_api.set_webhook(webhook_url)
    if result.get('success'):
        messages.success(request, f'تم تعيين webhook بنجاح: {webhook_url}')
    else:
        messages.error(request, f"فشل تعيين webhook: {result.get('error', 'خطأ غير معروف')}")
    return redirect('dashboard:whatsapp_connect')


@staff_member_required
def agent_settings(request):
    """صفحة إعدادات الوكيل"""
    settings = AgentSettings.get_active()
    if not settings:
        settings = AgentSettings.objects.create()
    
    if request.method == 'POST':
        settings.name = request.POST.get('name') or settings.name
        settings.model_name = request.POST.get('model_name') or settings.model_name
        settings.system_prompt = request.POST.get('system_prompt') or settings.system_prompt
        
        # معالجة القيم الرقمية بأمان
        temp_value = request.POST.get('temperature', '').strip()
        if temp_value:
            try:
                settings.temperature = float(temp_value)
            except ValueError:
                pass
        
        max_tokens_value = request.POST.get('max_tokens', '').strip()
        if max_tokens_value:
            try:
                settings.max_tokens = int(max_tokens_value)
            except ValueError:
                pass
        
        settings.welcome_message = request.POST.get('welcome_message') or settings.welcome_message
        settings.save()
        
        messages.success(request, 'تم حفظ إعدادات الوكيل بنجاح.')
        return redirect('dashboard:agent_settings')
    
    return render(request, 'dashboard/agent_settings.html', {
        'settings': settings,
        'openai_configured': bool(os.environ.get('OPENAI_API_KEY')),
        'google_configured': bool(os.environ.get('GOOGLE_MAPS_API_KEY')),
        'whatsapp_configured': bool(os.environ.get('WHATSAPP_ACCESS_TOKEN')),
    })


@staff_member_required
def diag_test_vision(request):
    """صفحة تشخيص تحليل الصور — تختبر كل خطوة في السلسلة"""
    import json as json_mod
    import traceback

    if request.method == 'GET':
        html = """
        <html dir="rtl"><body style="font-family:monospace;padding:20px;">
        <h2>🔍 اختبار تحليل الصور (OpenAI Vision)</h2>
        <form method="POST" enctype="multipart/form-data">
            <input type="hidden" name="csrfmiddlewaretoken" value="{csrf}">
            <p><label>ارفع صورة للاختبار:</label><br>
            <input type="file" name="image" accept="image/*" required></p>
            <button type="submit" style="padding:10px 20px;font-size:16px;">🧪 اختبر التحليل</button>
        </form>
        </body></html>
        """.format(csrf=request.META.get('CSRF_COOKIE', ''))
        from django.middleware.csrf import get_token
        get_token(request)
        html = html.replace('{csrf}', get_token(request))
        return HttpResponse(html)

    # POST: test image analysis
    results = []
    try:
        # Step 1: Check OpenAI key
        api_key = os.environ.get('OPENAI_API_KEY', '')
        results.append(f"✅ OPENAI_API_KEY set: {bool(api_key)} (len={len(api_key)})")

        # Step 2: Check client
        from ai_agent.media import _client, analyze_image_from_base64
        results.append(f"✅ OpenAI client initialized: {_client is not None}")

        if not _client:
            results.append("❌ OpenAI client is None — API key missing at import time!")
            return HttpResponse('<br>'.join(results), content_type='text/html')

        # Step 3: Read uploaded image
        image_file = request.FILES.get('image')
        if not image_file:
            results.append("❌ No image uploaded")
            return HttpResponse('<br>'.join(results), content_type='text/html')

        import base64 as b64mod
        image_bytes = image_file.read()
        image_base64 = b64mod.b64encode(image_bytes).decode('utf-8')
        mime_type = image_file.content_type or 'image/jpeg'
        results.append(f"✅ Image read: {image_file.name}, size={len(image_bytes)} bytes, mime={mime_type}, base64_len={len(image_base64)}")

        # Step 4: Call analyze
        results.append("⏳ Calling analyze_image_from_base64...")
        analysis = analyze_image_from_base64(image_base64, mime_type)

        if analysis:
            results.append(f"✅ Analysis SUCCESS!")
            results.append(f"📦 Product: {analysis.get('product_name_ar', 'N/A')}")
            results.append(f"🏪 Category: {analysis.get('category', 'N/A')}")
            results.append(f"🔍 Search: {analysis.get('search_query', 'N/A')}")
            results.append(f"📝 Description: {analysis.get('description', 'N/A')}")
            results.append(f"<br>Full result:<br><pre>{json_mod.dumps(analysis, ensure_ascii=False, indent=2)}</pre>")
        else:
            results.append("❌ Analysis returned None — check server logs for [MEDIA] errors")

    except Exception as e:
        results.append(f"❌ Exception: {type(e).__name__}: {e}")
        results.append(f"<pre>{traceback.format_exc()}</pre>")

    html = f"""<html dir="rtl"><body style="font-family:monospace;padding:20px;">
    <h2>🔍 نتائج اختبار تحليل الصور</h2>
    {'<br>'.join(results)}
    <br><br><a href="?">⬅️ رجوع</a>
    </body></html>"""
    return HttpResponse(html)
