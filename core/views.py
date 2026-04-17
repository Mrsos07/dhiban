from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib import messages
from django.http import FileResponse, Http404
from pathlib import Path


def landing_page(request):
    return render(request, 'landing.html')


_STATIC_DIR = Path(__file__).resolve().parent.parent / 'static'


def serve_logo(request, filename):
    """Serve logo/favicon directly — bypasses Cloudflare /static/ issues."""
    allowed = {'logo.png': 'image/png', 'logo.svg': 'image/svg+xml'}
    content_type = allowed.get(filename)
    if not content_type:
        raise Http404
    filepath = _STATIC_DIR / 'images' / filename
    if not filepath.is_file():
        raise Http404
    return FileResponse(open(filepath, 'rb'), content_type=content_type)


def admin_login(request):
    if request.user.is_authenticated:
        return redirect('/admin/')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            if user.is_staff:
                login(request, user)
                return redirect('/admin/')
            else:
                messages.error(request, 'ليس لديك صلاحية الوصول إلى لوحة الإدارة.')
        else:
            messages.error(request, 'اسم المستخدم أو كلمة المرور غير صحيحة.')
    
    return render(request, 'admin_login.html')
