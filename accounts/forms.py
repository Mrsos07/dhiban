from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from .models import CustomUser


class SecureLoginForm(forms.Form):
    """نموذج تسجيل دخول آمن مع التحقق من صحة البيانات"""
    
    email = forms.EmailField(
        label=_('البريد الإلكتروني'),
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'example@email.com',
            'autocomplete': 'email',
            'dir': 'ltr'
        })
    )
    password = forms.CharField(
        label=_('كلمة المرور'),
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'أدخل كلمة المرور',
            'autocomplete': 'current-password'
        })
    )
    remember_me = forms.BooleanField(
        label=_('تذكرني'),
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        })
    )
    
    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user_cache = None
        super().__init__(*args, **kwargs)
    
    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get('email')
        password = cleaned_data.get('password')
        
        if email and password:
            # التحقق من وجود المستخدم
            try:
                user = CustomUser.objects.get(email=email)
                
                # التحقق من قفل الحساب
                if user.is_locked:
                    from django.utils import timezone
                    if user.locked_until and user.locked_until > timezone.now():
                        remaining = (user.locked_until - timezone.now()).seconds // 60
                        raise ValidationError(
                            _('الحساب مقفل مؤقتاً. يرجى المحاولة بعد %(minutes)d دقيقة.'),
                            code='account_locked',
                            params={'minutes': remaining + 1}
                        )
                    else:
                        user.reset_failed_attempts()
                
            except CustomUser.DoesNotExist:
                pass
            
            # محاولة المصادقة
            self.user_cache = authenticate(
                self.request,
                email=email,
                password=password
            )
            
            if self.user_cache is None:
                raise ValidationError(
                    _('البريد الإلكتروني أو كلمة المرور غير صحيحة.'),
                    code='invalid_login'
                )
            
            if not self.user_cache.is_active:
                raise ValidationError(
                    _('هذا الحساب غير مفعّل.'),
                    code='inactive'
                )
            
            if not self.user_cache.is_staff:
                raise ValidationError(
                    _('ليس لديك صلاحية الوصول إلى لوحة الإدارة.'),
                    code='no_permission'
                )
        
        return cleaned_data
    
    def get_user(self):
        return self.user_cache


class UserCreationForm(forms.ModelForm):
    """نموذج إنشاء مستخدم جديد"""
    
    password1 = forms.CharField(
        label=_('كلمة المرور'),
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )
    password2 = forms.CharField(
        label=_('تأكيد كلمة المرور'),
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )
    
    class Meta:
        model = CustomUser
        fields = ('email', 'first_name', 'last_name', 'phone_number', 'role')
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'form-control', 'dir': 'ltr'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control', 'dir': 'ltr'}),
            'role': forms.Select(attrs={'class': 'form-select'}),
        }
    
    def clean_password2(self):
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            raise ValidationError(_('كلمتا المرور غير متطابقتين.'))
        return password2
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
        return user
