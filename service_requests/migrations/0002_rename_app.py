from django.db import migrations


class Migration(migrations.Migration):
    """
    إعادة تسمية الـ app من requests إلى service_requests
    الجدول موجود في قاعدة البيانات باسم requests_servicerequest
    """

    dependencies = [
        ('service_requests', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_name = 'requests_servicerequest'
                    ) AND NOT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_name = 'service_requests_servicerequest'
                    ) THEN
                        ALTER TABLE requests_servicerequest RENAME TO service_requests_servicerequest;
                        ALTER INDEX IF EXISTS requests_se_user_id_b4032b_idx RENAME TO service_requests_se_user_id_b4032b_idx;
                        ALTER INDEX IF EXISTS requests_se_categor_3da0ca_idx RENAME TO service_requests_se_categor_3da0ca_idx;
                        ALTER INDEX IF EXISTS requests_se_status_c390f9_idx RENAME TO service_requests_se_status_c390f9_idx;
                    END IF;
                END $$;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
