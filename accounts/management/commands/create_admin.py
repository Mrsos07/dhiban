"""
أمر إدارة لإنشاء مستخدم إداري من متغيرات البيئة
"""
import os
from django.core.management.base import BaseCommand
from accounts.models import CustomUser


class Command(BaseCommand):
    help = 'إنشاء مستخدم إداري من متغيرات البيئة'

    def add_arguments(self, parser):
        parser.add_argument(
            '--email',
            type=str,
            help='البريد الإلكتروني للمستخدم',
        )
        parser.add_argument(
            '--password',
            type=str,
            help='كلمة المرور',
        )
        parser.add_argument(
            '--name',
            type=str,
            default='Admin',
            help='اسم المستخدم',
        )

    def handle(self, *args, **options):
        # الحصول على البيانات من الأوامر أو متغيرات البيئة
        email = options.get('email') or os.environ.get('ADMIN_EMAIL')
        password = options.get('password') or os.environ.get('ADMIN_PASSWORD')
        name = options.get('name') or os.environ.get('ADMIN_NAME', 'Admin')
        
        if not email:
            self.stdout.write(self.style.ERROR('❌ يجب تحديد البريد الإلكتروني (--email أو ADMIN_EMAIL)'))
            return
        
        if not password:
            self.stdout.write(self.style.ERROR('❌ يجب تحديد كلمة المرور (--password أو ADMIN_PASSWORD)'))
            return
        
        # التحقق من وجود المستخدم
        if CustomUser.objects.filter(email=email).exists():
            self.stdout.write(self.style.WARNING(f'⚠️ المستخدم {email} موجود مسبقاً'))
            
            # تحديث كلمة المرور إذا طُلب
            user = CustomUser.objects.get(email=email)
            user.set_password(password)
            user.is_staff = True
            user.is_superuser = True
            user.is_active = True
            user.save()
            self.stdout.write(self.style.SUCCESS(f'✅ تم تحديث كلمة المرور للمستخدم {email}'))
            return
        
        # إنشاء المستخدم الجديد
        user = CustomUser.objects.create_superuser(
            email=email,
            password=password,
            first_name=name,
        )
        
        self.stdout.write(self.style.SUCCESS(f'✅ تم إنشاء المستخدم الإداري: {email}'))
