from django.utils.deprecation import MiddlewareMixin
from django.shortcuts import redirect
from django.contrib import messages
from django.utils import timezone
from django.conf import settings
from datetime import datetime


class SessionTimeoutMiddleware(MiddlewareMixin):
    """Middleware للتحكم في انتهاء صلاحية الجلسة"""
    
    def process_request(self, request):
        if request.user.is_authenticated:
            last_activity = request.session.get('last_activity')
            
            if last_activity:
                try:
                    last_activity_time = datetime.fromisoformat(last_activity)
                    
                    if timezone.is_naive(last_activity_time):
                        last_activity_time = timezone.make_aware(last_activity_time)
                    
                    idle_time = (timezone.now() - last_activity_time).total_seconds()
                    timeout = getattr(settings, 'SESSION_IDLE_TIMEOUT', 1800)
                    
                    if idle_time > timeout and not request.session.get('remember_me'):
                        from django.contrib.auth import logout
                        logout(request)
                        messages.warning(request, 'انتهت صلاحية الجلسة. يرجى تسجيل الدخول مرة أخرى.')
                        return redirect('admin_login')
                except (ValueError, TypeError):
                    pass
            
            request.session['last_activity'] = timezone.now().isoformat()
        
        return None


class SecurityHeadersMiddleware(MiddlewareMixin):
    """Middleware لإضافة رؤوس الأمان"""
    
    def process_response(self, request, response):
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY'
        response['X-XSS-Protection'] = '1; mode=block'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        if not settings.DEBUG:
            response['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        
        return response


class AdminAccessMiddleware(MiddlewareMixin):
    """Middleware للتحقق من صلاحيات الوصول للإدارة"""
    
    def process_request(self, request):
        if request.path.startswith('/admin/') and not request.path.startswith('/admin/login/'):
            if not request.user.is_authenticated:
                return redirect('admin_login')
            
            if not request.user.is_staff:
                messages.error(request, 'ليس لديك صلاحية الوصول إلى لوحة الإدارة.')
                return redirect('landing')
        
        return None
