# دليل نشر ذيبان على Render

## المتطلبات
- حساب على [Render](https://render.com)
- حساب على [GitHub](https://github.com)
- مفاتيح API:
  - OpenAI API Key
  - Google Maps API Key
  - WhatsApp Business API (اختياري)

---

## خطوات النشر

### 1. رفع المشروع على GitHub

```bash
# إذا لم يكن لديك Git مُعد
git init
git add .
git commit -m "Initial commit - Dhiban AI Agent"

# ربط المستودع بـ GitHub
git remote add origin https://github.com/USERNAME/dhiban.git
git branch -M main
git push -u origin main
```

### 2. إنشاء خدمة على Render

#### الطريقة الأولى: Blueprint (الأسهل)
1. اذهب إلى [Render Dashboard](https://dashboard.render.com)
2. اضغط على **New** → **Blueprint**
3. اختر مستودع GitHub الخاص بك
4. Render سيقرأ ملف `render.yaml` ويُنشئ الخدمات تلقائياً

#### الطريقة الثانية: يدوياً
1. اذهب إلى [Render Dashboard](https://dashboard.render.com)
2. اضغط على **New** → **Web Service**
3. اختر **Build and deploy from a Git repository**
4. اربط حساب GitHub واختر المستودع
5. أدخل الإعدادات التالية:

| الإعداد | القيمة |
|---------|--------|
| Name | dhiban |
| Runtime | Docker |
| Dockerfile Path | ./Dockerfile |
| Instance Type | Free |

### 3. إعداد قاعدة البيانات

1. اضغط على **New** → **PostgreSQL**
2. أدخل الإعدادات:
   - Name: `dhiban-db`
   - Database: `dhiban`
   - User: `dhiban_user`
   - Plan: Free

3. انسخ **Internal Database URL**

### 4. إعداد المتغيرات البيئية

في صفحة Web Service، اذهب إلى **Environment**:

| المتغير | القيمة |
|---------|--------|
| `DEBUG` | `False` |
| `SECRET_KEY` | (سيتم توليده تلقائياً) |
| `ALLOWED_HOSTS` | `.onrender.com` |
| `DATABASE_URL` | (من قاعدة البيانات) |
| `OPENAI_API_KEY` | `sk-...` |
| `GOOGLE_MAPS_API_KEY` | `AIza...` |
| `WHATSAPP_ACCESS_TOKEN` | (اختياري) |
| `WHATSAPP_PHONE_NUMBER_ID` | (اختياري) |
| `WHATSAPP_VERIFY_TOKEN` | (اختياري) |

### 5. النشر

1. اضغط على **Manual Deploy** → **Deploy latest commit**
2. انتظر حتى يكتمل البناء (5-10 دقائق)
3. بعد النجاح، ستحصل على رابط مثل: `https://dhiban.onrender.com`

### 6. إعداد قاعدة البيانات

بعد النشر، قم بتشغيل الأوامر التالية من Shell في Render:

```bash
# تشغيل Migrations
python manage.py migrate

# إنشاء التصنيفات الافتراضية
python manage.py setup_categories

# إنشاء مستخدم إداري
python manage.py createsuperuser
```

---

## الملفات المهمة

| الملف | الوصف |
|-------|-------|
| `Dockerfile` | تعريف Docker للبناء |
| `render.yaml` | Blueprint لـ Render |
| `build.sh` | سكريبت البناء |
| `requirements.txt` | المكتبات المطلوبة |

---

## استكشاف الأخطاء

### خطأ في قاعدة البيانات
- تأكد من أن `DATABASE_URL` صحيح
- تأكد من تشغيل `python manage.py migrate`

### خطأ في الملفات الثابتة
- تأكد من تشغيل `python manage.py collectstatic`
- تأكد من وجود WhiteNoise في MIDDLEWARE

### خطأ 500
- تأكد من `DEBUG=False`
- تحقق من Logs في Render

---

## التحديث

لتحديث التطبيق:

```bash
git add .
git commit -m "Update description"
git push origin main
```

Render سيقوم بالنشر التلقائي.

---

## الدعم

للمساعدة، تواصل عبر:
- البريد: info@dhiban.sa
- واتساب: +966 50 000 0000
