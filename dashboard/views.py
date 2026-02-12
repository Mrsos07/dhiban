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
from requests.models import ServiceRequest
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
    
    context = {
        'stats': stats,
        'recent_users': recent_users,
        'recent_suppliers': recent_suppliers,
        'chart_labels': json.dumps(chart_labels),
        'chart_conversations': json.dumps(chart_conversations),
        'chart_requests': json.dumps(chart_requests),
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
    """قائمة التصنيفات"""
    categories = Category.objects.annotate(suppliers_count=Count('suppliers'))
    return render(request, 'dashboard/categories_list.html', {'categories': categories})


@staff_member_required
def category_add(request):
    """إضافة تصنيف"""
    if request.method == 'POST':
        Category.objects.create(
            name_ar=request.POST.get('name_ar'),
            name_en=request.POST.get('name_en', ''),
            icon=request.POST.get('icon', 'folder'),
        )
        messages.success(request, 'تم إضافة التصنيف بنجاح.')
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
        message = data.get('message', '')
        
        if not message:
            return JsonResponse({'error': 'الرسالة مطلوبة'}, status=400)
        
        from ai_agent.agent import process_user_message
        response = process_user_message(message)
        
        return JsonResponse({'response': response})
    
    except Exception as e:
        return JsonResponse({'error': str(e), 'response': 'حدث خطأ في معالجة الرسالة.'}, status=500)


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
