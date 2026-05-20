"""
Run this once to migrate data from inventory.db (SQLite) to MongoDB Atlas.
Usage: python migrate_sqlite_to_mongo.py [path/to/inventory.db]
"""
import sys
import os
import sqlite3
from datetime import datetime, date

# Load .env
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

# Bootstrap Flask app (connects to MongoDB)
from app import create_app, bcrypt
app = create_app()

DB_PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), 'inventory.db')

if not os.path.exists(DB_PATH):
    print(f'ERROR: SQLite database not found at {DB_PATH}')
    sys.exit(1)

print(f'Migrating from: {DB_PATH}')
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()


def _dt(val):
    if not val:
        return None
    for fmt in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(val, fmt)
        except (ValueError, TypeError):
            pass
    return None


def _date(val):
    if not val:
        return None
    try:
        return date.fromisoformat(val[:10])
    except (ValueError, TypeError):
        return None


with app.app_context():
    from app.models.user import User
    from app.models.site import Site
    from app.models.asset import Asset, AssetType, AssetEvent
    from app.models.task import Task
    from app.models.contact import Contact
    from app.models.estimate import Estimate, EstimateItem
    from app.models.settings import AppSetting

    # ── id maps (sqlite int → mongo ObjectId) ─────────────────────────────────
    user_map      = {}
    site_map      = {}
    asset_map     = {}
    asset_type_map= {}

    # ── Users ──────────────────────────────────────────────────────────────────
    print('Migrating users...')
    for row in cur.execute('SELECT * FROM users').fetchall():
        u = User(
            name=row['name'],
            email=row['email'],
            password_hash=row['password_hash'],
            role=row['role'],
            created_at=_dt(row['created_at']) or datetime.utcnow(),
        )
        u.save()
        user_map[row['id']] = u
    print(f'  {len(user_map)} users migrated')

    # ── Sites ──────────────────────────────────────────────────────────────────
    print('Migrating sites...')
    for row in cur.execute('SELECT * FROM sites').fetchall():
        s = Site(name=row['name'], address=row['address'], notes=row['notes'])
        s.save()
        site_map[row['id']] = s
    print(f'  {len(site_map)} sites migrated')

    # ── Asset Types ────────────────────────────────────────────────────────────
    print('Migrating asset types...')
    for row in cur.execute('SELECT * FROM asset_types').fetchall():
        at = AssetType(name=row['name'], category=row['category'])
        at.save()
        asset_type_map[row['id']] = at
    print(f'  {len(asset_type_map)} asset types migrated')

    # ── Assets ─────────────────────────────────────────────────────────────────
    print('Migrating assets...')
    for row in cur.execute('SELECT * FROM assets').fetchall():
        a = Asset(
            component_id   = row['component_id'],
            serial_number  = row['serial_number'],
            barcode        = row['barcode'],
            asset_type     = asset_type_map.get(row['asset_type_id']),
            model          = row['model'],
            manufacturer   = row['manufacturer'],
            status         = row['status'] or 'in_storage',
            current_site   = site_map.get(row['current_site_id']),
            assignee       = user_map.get(row['assigned_to_id']),
            notes          = row['notes'],
            price          = row['price'],
            price_nis      = row['price_nis'],
            price_usd      = row['price_usd'],
            conversion_fee = row['conversion_fee'],
            quantity       = row['quantity'],
            min_threshold  = row['min_threshold'],
            created_at     = _dt(row['created_at']) or datetime.utcnow(),
        )
        a.save()
        asset_map[row['id']] = a
    print(f'  {len(asset_map)} assets migrated')

    # ── Asset Events ───────────────────────────────────────────────────────────
    print('Migrating asset events...')
    event_count = 0
    for row in cur.execute('SELECT * FROM asset_events').fetchall():
        asset = asset_map.get(row['asset_id'])
        performer = user_map.get(row['performed_by_id'])
        if not asset or not performer:
            continue
        e = AssetEvent(
            asset             = asset,
            event_type        = row['event_type'],
            from_site         = site_map.get(row['from_site_id']),
            to_site           = site_map.get(row['to_site_id']),
            performed_by_user = performer,
            notes             = row['notes'],
            event_date        = _dt(row['event_date']) or datetime.utcnow(),
        )
        e.save()
        event_count += 1
    print(f'  {event_count} events migrated')

    # ── Tasks ──────────────────────────────────────────────────────────────────
    print('Migrating tasks...')
    task_count = 0
    for row in cur.execute('SELECT * FROM tasks').fetchall():
        t = Task(
            title      = row['title'],
            asset      = asset_map.get(row['asset_id']),
            assignee   = user_map.get(row['assigned_to_id']),
            status     = row['status'] or 'pending',
            notes      = row['notes'],
            created_at = _dt(row['created_at']) or datetime.utcnow(),
        )
        t.save()
        task_count += 1
    print(f'  {task_count} tasks migrated')

    # ── Contacts ───────────────────────────────────────────────────────────────
    print('Migrating contacts...')
    contact_map = {}
    try:
        for row in cur.execute('SELECT * FROM contacts').fetchall():
            c = Contact(
                name       = row['name'],
                email      = row['email'],
                phone      = row['phone'],
                notes      = row['notes'],
                created_at = _dt(row['created_at']) or datetime.utcnow(),
            )
            c.save()
            contact_map[row['id']] = c
        print(f'  {len(contact_map)} contacts migrated')
    except Exception as ex:
        print(f'  contacts skipped: {ex}')

    # ── Estimates ──────────────────────────────────────────────────────────────
    print('Migrating estimates...')
    est_count = 0
    try:
        for row in cur.execute('SELECT * FROM estimates').fetchall():
            est = Estimate(
                allocation_number = row['allocation_number'],
                status            = row['status'] or 'pending',
                task_name         = row['task_name'],
                project_name      = row['project_name'],
                created_date      = _date(row['created_date']),
                valid_until       = _date(row['valid_until']),
                usd_rate          = float(row['usd_rate'] or 3.0),
                total_nis         = float(row['total_nis']) if row['total_nis'] else None,
                created_by        = user_map.get(row['created_by_id']),
                created_at        = _dt(row['created_at']) or datetime.utcnow(),
            )
            # Estimate items
            for irow in cur.execute('SELECT * FROM estimate_items WHERE estimate_id=?', (row['id'],)).fetchall():
                asset = asset_map.get(irow['asset_id'])
                if asset:
                    est.items.append(EstimateItem(
                        asset=asset,
                        quantity=irow['quantity'],
                        unit_price_usd=float(irow['unit_price_usd']) if irow['unit_price_usd'] else None,
                    ))
            est.save()
            est_count += 1
        print(f'  {est_count} estimates migrated')
    except Exception as ex:
        print(f'  estimates skipped: {ex}')

    # ── App Settings ───────────────────────────────────────────────────────────
    print('Migrating app settings...')
    try:
        for row in cur.execute('SELECT * FROM app_settings').fetchall():
            if not AppSetting.objects(key=row['key']).first():
                AppSetting(key=row['key'], value=row['value']).save()
        print('  settings migrated')
    except Exception as ex:
        print(f'  settings skipped: {ex}')

conn.close()
print('\nMigration complete!')
