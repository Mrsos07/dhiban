from django.db import migrations


class Migration(migrations.Migration):
    """
    الجدول موجود باسم requests_servicerequest - db_table في models.py يتعامل معه
    """

    dependencies = [
        ('service_requests', '0001_initial'),
    ]

    operations = []
