from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_protect
from datetime import timedelta
from .forms import SecureLoginForm
from .models import CustomUser, LoginAttempt


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def log_login_attempt(request, email, successful, user=None, failure_reason=''):
    LoginAttempt.objects.create(
        user=user,
        email=email,
        ip_address=get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
        successful=successful,
        failure_reason=failure_reason
    )


def handle_failed_login(email):
    try:
        user = CustomUser.objects.get(email=email)
        user.failed_login_attempts += 1
        user.last_failed_login = timezone.now()
        
        if user.failed_login_attempts >= 5:
            user.is_locked = True
            user.locked_until = timezone.now() + timedelta(minutes=15)
        
        user.save(update_fields=['failed_login_attempts', 'last_failed_login', 'is_locked', 'locked_until'])
        return user
    except CustomUser.DoesNotExist:
        return None


@csrf_protect
@require_http_methods(['GET', 'POST'])
def admin_login_view(request):
    if request.user.is_authenticated and request.user.is_staff:
        return redirect('/dashboard/')
    
    if request.method == 'POST':
        form = SecureLoginForm(request, data=request.POST)
        
        if form.is_valid():
            user = form.get_user()
            
            log_login_attempt(request, user.email, True, user)
            user.reset_failed_attempts()
            
            login(request, user)
            
            if form.cleaned_data.get('remember_me'):
                request.session.set_expiry(60 * 60 * 24 * 30)
                request.session['remember_me'] = True
            else:
                request.session.set_expiry(60 * 30)
            
            messages.success(request, f'مرحباً {user.get_full_name()}!')
            return redirect('/dashboard/')
        else:
            email = request.POST.get('email', '')
            user = handle_failed_login(email)
            log_login_attempt(request, email, False, user, 'بيانات غير صحيحة')
    else:
        form = SecureLoginForm(request)
    
    return render(request, 'accounts/login.html', {'form': form})


@require_http_methods(['POST'])
def admin_logout_view(request):
    logout(request)
    messages.info(request, 'تم تسجيل الخروج بنجاح.')
    return redirect('accounts:admin_login')
