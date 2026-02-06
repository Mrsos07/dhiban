from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib import messages


def landing_page(request):
    return render(request, 'landing.html')


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
