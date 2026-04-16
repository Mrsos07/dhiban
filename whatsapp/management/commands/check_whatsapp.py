"""
أداة تشخيص WhatsApp/Evolution API:
  - تعرض حالة الاتصال
  - تعرض إعدادات webhook الحالية على Evolution
  - تقارنها مع EVOLUTION_WEBHOOK_URL في الإعدادات
  - تعيد تعيين webhook تلقائياً إذا اختلف أو معطّل

الاستخدام:
    python manage.py check_whatsapp
    python manage.py check_whatsapp --fix
"""
import json
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = 'تشخيص اتصال WhatsApp/Evolution وفحص webhook + إصلاحه تلقائياً'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help='إعادة تعيين webhook إذا كان مختلفاً أو معطّلاً',
        )

    def handle(self, *args, **options):
        from whatsapp.evolution_api import evolution_api

        self.stdout.write(self.style.MIGRATE_HEADING('\n=== Evolution API Settings ==='))
        api_url = getattr(settings, 'EVOLUTION_API_URL', '') or '(NOT SET)'
        instance = getattr(settings, 'EVOLUTION_INSTANCE_NAME', '') or '(NOT SET)'
        webhook_url = getattr(settings, 'EVOLUTION_WEBHOOK_URL', '') or ''
        api_key = getattr(settings, 'EVOLUTION_API_KEY', '') or ''

        self.stdout.write(f'  EVOLUTION_API_URL        : {api_url}')
        self.stdout.write(f'  EVOLUTION_INSTANCE_NAME  : {instance}')
        self.stdout.write(f'  EVOLUTION_API_KEY        : {"****" + api_key[-4:] if api_key else "(NOT SET)"}')
        self.stdout.write(f'  EVOLUTION_WEBHOOK_URL    : {webhook_url or "(NOT SET — المشكلة هنا!)"}')

        if not webhook_url:
            self.stdout.write(self.style.ERROR(
                '\n✗ EVOLUTION_WEBHOOK_URL غير محدد في متغيرات البيئة!'
            ))
            self.stdout.write('  أضفه على Render بالقيمة:')
            self.stdout.write(self.style.WARNING(
                '    EVOLUTION_WEBHOOK_URL=https://<your-render-domain>/whatsapp/evolution/webhook/'
            ))
            return

        self.stdout.write(self.style.MIGRATE_HEADING('\n=== Connection Status ==='))
        status = evolution_api.get_connection_status() if hasattr(evolution_api, 'get_connection_status') else {}
        self.stdout.write(f'  {json.dumps(status, ensure_ascii=False, indent=2)}')

        self.stdout.write(self.style.MIGRATE_HEADING('\n=== Current Webhook on Evolution ==='))
        current = evolution_api.find_webhook()
        self.stdout.write(f'  {json.dumps(current, ensure_ascii=False, indent=2)}')

        # استخراج الحقول المهمة من الرد
        data = current.get('data') if isinstance(current, dict) else None
        if isinstance(data, dict):
            inner = data.get('webhook', data)
            current_url = inner.get('url', '') if isinstance(inner, dict) else ''
            enabled = inner.get('enabled', False) if isinstance(inner, dict) else False
            events = inner.get('events', []) if isinstance(inner, dict) else []
        else:
            current_url = ''
            enabled = False
            events = []

        self.stdout.write('\n--- تحليل ---')
        match = current_url.rstrip('/') == webhook_url.rstrip('/')
        has_messages_upsert = any(e.upper() == 'MESSAGES_UPSERT' for e in events)

        self.stdout.write(f'  Enabled        : {enabled}')
        self.stdout.write(f'  URL matches    : {match}  (current: {current_url or "NONE"})')
        self.stdout.write(f'  MESSAGES_UPSERT: {has_messages_upsert}')

        needs_fix = (not enabled) or (not match) or (not has_messages_upsert) or (not current_url)

        if not needs_fix:
            self.stdout.write(self.style.SUCCESS('\n✓ webhook صحيح — لا يحتاج تعديل.'))
            self.stdout.write('  لو الوكيل مازال ما يرد، تحقق من:')
            self.stdout.write('    1. لوق Render (اطلب من Evolution يبعث رسالة اختبار)')
            self.stdout.write('    2. تأكد أن نطاق Render يرد على GET /whatsapp/evolution/webhook/')
            return

        self.stdout.write(self.style.WARNING('\n⚠ webhook يحتاج إصلاح'))

        if not options['fix']:
            self.stdout.write('\n  شغّل الأمر مع --fix لإعادة التعيين:')
            self.stdout.write(self.style.WARNING(
                '    python manage.py check_whatsapp --fix'
            ))
            return

        self.stdout.write('\n→ إعادة تعيين webhook...')
        result = evolution_api.set_webhook(webhook_url)
        if result.get('success'):
            self.stdout.write(self.style.SUCCESS(f'✓ تم تعيين webhook: {webhook_url}'))
        else:
            self.stdout.write(self.style.ERROR(f'✗ فشل: {result.get("error")}'))
            self.stdout.write(f'  Body: {result.get("body")}')
