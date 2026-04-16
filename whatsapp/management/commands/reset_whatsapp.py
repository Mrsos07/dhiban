"""
إعادة ضبط instance WhatsApp عالق على Evolution API.

يمر بالخطوات التالية بترتيب متدرج ومتسامح مع الأخطاء:
  1. logout (قطع الجلسة)
  2. restart (إعادة تشغيل)
  3. delete (حذف الـ instance)
  4. create (إنشاء جديد مع webhook)
  5. set_webhook (تعيين webhook مرة أخرى للتأكيد)

الاستخدام:
    python manage.py reset_whatsapp              # تشخيص فقط
    python manage.py reset_whatsapp --force      # تنفيذ الحذف الكامل
    python manage.py reset_whatsapp --force --recreate   # حذف + إنشاء جديد
"""
import json
import time
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = 'تنظيف + إعادة إنشاء instance WhatsApp على Evolution API (لحل الحالات العالقة)'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true',
                            help='نفّذ فعلياً (بدون هذا الخيار يعمل dry-run فقط)')
        parser.add_argument('--recreate', action='store_true',
                            help='بعد الحذف، أنشئ instance جديد مع webhook')

    def _step(self, title):
        self.stdout.write(self.style.MIGRATE_HEADING(f'\n→ {title}'))

    def _ok(self, msg):
        self.stdout.write(self.style.SUCCESS(f'  ✓ {msg}'))

    def _warn(self, msg):
        self.stdout.write(self.style.WARNING(f'  ⚠ {msg}'))

    def _err(self, msg):
        self.stdout.write(self.style.ERROR(f'  ✗ {msg}'))

    def _dump(self, label, result):
        try:
            self.stdout.write(f'    {label}: {json.dumps(result, ensure_ascii=False)[:400]}')
        except Exception:
            self.stdout.write(f'    {label}: {result}')

    def handle(self, *args, **options):
        from whatsapp.evolution_api import evolution_api

        force = options['force']
        recreate = options['recreate']

        self.stdout.write(self.style.MIGRATE_HEADING('\n=== Evolution Instance Reset Tool ==='))
        self.stdout.write(f'  Instance : {evolution_api.instance_name}')
        self.stdout.write(f'  Base URL : {evolution_api.base_url}')
        self.stdout.write(f'  Mode     : {"FORCE (real changes)" if force else "DRY-RUN (read-only)"}')
        self.stdout.write(f'  Recreate : {recreate}')

        # 0) فحص أولي
        self._step('0) فحص الحالة الحالية')
        exists = evolution_api.instance_exists()
        self.stdout.write(f'  Instance exists : {exists}')
        try:
            status = evolution_api.get_instance_status()
            self._dump('connection status', status)
        except Exception as e:
            self._warn(f'status check failed: {e}')

        if not force:
            self._warn('\ndry-run فقط — أعد التشغيل مع --force للتنفيذ الفعلي.')
            return

        # 1) logout
        self._step('1) logout')
        r = evolution_api.logout_instance()
        if r.get('success'):
            self._ok('logout ok')
        else:
            self._warn(f'logout failed: status={r.get("status")} err={r.get("error")}')
        time.sleep(1)

        # 2) restart
        self._step('2) restart')
        try:
            r = evolution_api.restart_instance()
            if r.get('success'):
                self._ok('restart ok')
            else:
                self._warn(f'restart failed: status={r.get("status")} err={r.get("error")}')
        except Exception as e:
            self._warn(f'restart exception: {e}')
        time.sleep(2)

        # 3) delete
        self._step('3) delete')
        r = evolution_api.delete_instance()
        if r.get('success'):
            self._ok('delete ok')
        else:
            status = r.get('status')
            body = r.get('body') or {}
            self._err(f'delete failed: status={status} err={r.get("error")}')
            self._dump('body', body)
            # لو 404 يعني راح — نعتبرها نجحت
            if status == 404:
                self._ok('instance not found (already deleted)')
            else:
                self._warn('\nلو الخطأ استمر، الحل الأخير هو إعادة تشغيل خدمة Evolution نفسها '
                           'على Render (Manual Deploy / Restart Service).')
                return
        time.sleep(1)

        # 4) recreate
        if not recreate:
            self._step('تم الانتهاء (بدون recreate).')
            self._ok('شغّل الأمر مع --recreate لإنشاء instance جديد فوراً.')
            return

        self._step('4) create new instance')
        r = evolution_api.create_instance()
        if r.get('success'):
            self._ok('instance created')
            self._dump('data', r.get('data'))
        else:
            self._err(f'create failed: status={r.get("status")} err={r.get("error")}')
            self._dump('body', r.get('body'))
            return
        time.sleep(2)

        # 5) set webhook
        webhook_url = getattr(settings, 'EVOLUTION_WEBHOOK_URL', '')
        if webhook_url:
            self._step('5) set webhook')
            r = evolution_api.set_webhook(webhook_url)
            if r.get('success'):
                self._ok(f'webhook set: {webhook_url}')
            else:
                self._err(f'set_webhook failed: {r.get("error")}')
        else:
            self._warn('EVOLUTION_WEBHOOK_URL غير محدد — تخطّي خطوة set_webhook.')

        self.stdout.write(self.style.SUCCESS('\n=== ✓ تمت العملية ==='))
        self.stdout.write('الخطوة التالية: افتح /dashboard/whatsapp/ وامسح QR code الجديد.')
