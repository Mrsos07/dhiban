# ذيبان - الدليل الذكي

موقع تعريفي لمشروع ذيبان - الدليل الذكي مبني بـ Django و Bootstrap 5.

## المتطلبات

- Python 3.10+
- PostgreSQL

## التثبيت

1. تفعيل البيئة الافتراضية:
   ```
   .\env\Scripts\activate
   ```

2. تثبيت المتطلبات:
   ```
   pip install -r requirements.txt
   ```

3. إعداد قاعدة البيانات PostgreSQL وتحديث settings.py

4. تشغيل migrations:
   ```
   python manage.py migrate
   ```

5. إنشاء مستخدم إداري:
   ```
   python manage.py createsuperuser
   ```

6. تشغيل الخادم:
   ```
   python manage.py runserver
   ```

## الهيكل

- / - صفحة الهبوط
- /admin-login/ - تسجيل دخول الإدارة
- /admin/ - لوحة التحكم
