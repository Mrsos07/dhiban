"""
Startup script for Render deployment.
Handles the case where production DB has tables/columns
but django_migrations table is out of sync.
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dhiban_project.settings')
django.setup()

from django.core.management import call_command
from django.db import connection


def get_applied_migrations():
    """Get set of already-applied migrations from django_migrations table."""
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT app, name FROM django_migrations"
            )
            return {(row[0], row[1]) for row in cursor.fetchall()}
    except Exception:
        return set()


def table_exists(table_name):
    """Check if a table exists in the database."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = %s)",
            [table_name]
        )
        return cursor.fetchone()[0]


def column_exists(table_name, column_name):
    """Check if a column exists in a table."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT EXISTS (SELECT FROM information_schema.columns "
            "WHERE table_name = %s AND column_name = %s)",
            [table_name, column_name]
        )
        return cursor.fetchone()[0]


def smart_migrate():
    """
    Smart migration strategy:
    1. Check if django_migrations table exists
    2. If tables exist but migrations aren't recorded, fake them
    3. Then run normal migrate for any truly new migrations
    """
    print("[startup] Checking database state...")

    # Check if key tables already exist in DB
    key_tables = {
        'accounts':         'accounts_adminuser',
        'ai_agent':         'ai_agent_agentsettings',
        'conversations':    'conversations_conversation',
        'service_requests': 'service_requests_servicerequest',
        'suppliers':        'suppliers_supplier',
        'users':            'users_whatsappuser',
    }

    applied = get_applied_migrations()
    print(f"[startup] Found {len(applied)} applied migrations in DB")

    # For each app: if table exists but initial migration not recorded, fake it
    needs_fake = []
    for app, table in key_tables.items():
        if table_exists(table) and (app, '0001_initial') not in applied:
            needs_fake.append(app)
            print(f"[startup] Table '{table}' exists but migration not recorded -> will fake {app}")

    if needs_fake:
        # Fake ALL migrations for apps whose tables exist
        # This marks everything as applied without running SQL
        for app in needs_fake:
            print(f"[startup] Faking all migrations for '{app}'...")
            try:
                call_command('migrate', app, '--fake', '--noinput', verbosity=0)
            except Exception as e:
                print(f"[startup] Warning faking {app}: {e}")

    # Check for specific columns from newer migrations.
    # Case 1: column exists but migration NOT recorded -> fake it
    # Case 2: column missing but migration IS recorded -> un-fake so it gets applied
    new_columns = [
        ('suppliers', 'suppliers_supplier', 'google_maps_url', '0002_add_google_maps_url'),
        ('suppliers', 'suppliers_supplier', 'customer_category', '0003_add_customer_category_tags_agent_notes'),
        ('users', 'users_whatsappuser', 'customer_category', '0002_add_customer_category_tags_agent_notes'),
    ]

    for app, table, col, migration_name in new_columns:
        col_exists = column_exists(table, col)
        migration_recorded = (app, migration_name) in get_applied_migrations()

        if col_exists and not migration_recorded:
            # Column already exists in DB but migration not recorded -> fake it
            print(f"[startup] Column '{col}' exists but migration not recorded -> faking {app} {migration_name}...")
            try:
                call_command('migrate', app, migration_name, '--fake', '--noinput', verbosity=0)
            except Exception as e:
                print(f"[startup] Warning faking {app} {migration_name}: {e}")

        elif not col_exists and migration_recorded:
            # Column missing but migration marked as applied -> un-fake so migrate re-applies it
            print(f"[startup] Column '{col}' missing in '{table}' but migration recorded -> un-faking...")
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "DELETE FROM django_migrations WHERE app = %s AND name = %s",
                        [app, migration_name]
                    )
            except Exception as e:
                print(f"[startup] Warning un-faking: {e}")

    # Now run normal migrate - this applies any genuinely new migrations
    print("[startup] Running normal migrate...")
    call_command('migrate', '--noinput')
    print("[startup] Migrations complete!")


if __name__ == '__main__':
    smart_migrate()
