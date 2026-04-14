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

    # Check newer migrations by inspecting ALL their columns.
    # For each migration: collect all (table, column) pairs it adds.
    # Decision logic:
    #   - If migration NOT recorded AND at least one column exists -> fake it (columns already there)
    #   - If migration IS recorded AND some columns are missing -> add missing columns via raw SQL
    #   - If migration NOT recorded AND no columns exist -> let normal migrate handle it
    migration_columns = [
        ('suppliers', '0002_add_google_maps_url', [
            ('suppliers_supplier', 'google_maps_url', 'VARCHAR(500) DEFAULT \'\''),
        ]),
        ('suppliers', '0003_add_customer_category_tags_agent_notes', [
            ('suppliers_supplier', 'customer_category', 'VARCHAR(100) DEFAULT \'\''),
            ('suppliers_supplier', 'tags', 'TEXT DEFAULT \'[]\''),
            ('suppliers_supplier', 'agent_notes', 'TEXT DEFAULT \'\''),
        ]),
        ('users', '0002_add_customer_category_tags_agent_notes', [
            ('users_whatsappuser', 'customer_category', 'VARCHAR(100) DEFAULT \'\''),
            ('users_whatsappuser', 'tags', 'TEXT DEFAULT \'[]\''),
            ('users_whatsappuser', 'agent_notes', 'TEXT DEFAULT \'\''),
        ]),
    ]

    applied = get_applied_migrations()  # refresh after fake operations above

    for app, migration_name, cols in migration_columns:
        migration_recorded = (app, migration_name) in applied
        existing = [(t, c) for t, c, _ in cols if column_exists(t, c)]
        missing  = [(t, c, sql) for t, c, sql in cols if not column_exists(t, c)]

        if not migration_recorded and existing:
            # At least one column already in DB but migration not recorded -> fake
            print(f"[startup] Faking {app} {migration_name} ({len(existing)}/{len(cols)} columns exist)...")
            try:
                call_command('migrate', app, migration_name, '--fake', '--noinput', verbosity=0)
            except Exception as e:
                print(f"[startup] Warning faking {app} {migration_name}: {e}")
            # After faking, add any truly missing columns via raw SQL
            for table, col, col_sql in missing:
                print(f"[startup] Adding missing column '{col}' to '{table}' via SQL...")
                try:
                    with connection.cursor() as cursor:
                        cursor.execute(f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS "{col}" {col_sql}')
                except Exception as e:
                    print(f"[startup] Warning adding column {col}: {e}")

        elif migration_recorded and missing:
            # Migration recorded but some columns missing -> add them via raw SQL
            for table, col, col_sql in missing:
                print(f"[startup] Migration recorded but column '{col}' missing -> adding via SQL...")
                try:
                    with connection.cursor() as cursor:
                        cursor.execute(f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS "{col}" {col_sql}')
                except Exception as e:
                    print(f"[startup] Warning adding column {col}: {e}")

    # Now run normal migrate - this applies any genuinely new migrations
    print("[startup] Running normal migrate...")
    call_command('migrate', '--noinput')
    print("[startup] Migrations complete!")


if __name__ == '__main__':
    smart_migrate()
