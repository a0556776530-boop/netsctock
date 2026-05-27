"""
One-time migration: replace all AssetType records with the 8 canonical categories,
and delete any assets whose type is no longer in the canonical list.
"""
import os
from dotenv import load_dotenv
load_dotenv()

from app import create_app
app = create_app()

CANONICAL = [
    'Routers', 'Aggregation', 'Access switches', 'Sfp', 'Cards',
    'Power supplies', 'Power cords', 'Console cables',
]

with app.app_context():
    from app.models.asset import Asset, AssetType, AssetEvent

    existing = list(AssetType.objects)
    existing_names = {t.name for t in existing}

    # ── 1. Create missing canonical types ─────────────────────────────────────
    for name in CANONICAL:
        if name not in existing_names:
            AssetType(name=name).save()
            print(f'  [+] Created AssetType: {name}')
        else:
            print(f'  [=] Already exists:    {name}')

    # ── 2. Find old types not in canonical list ────────────────────────────────
    old_types = [t for t in existing if t.name not in CANONICAL]
    if not old_types:
        print('\n  No old types to remove.')
    else:
        print(f'\n  Old types to remove ({len(old_types)}):')
        for t in old_types:
            assets_using = list(Asset.objects(asset_type=t))
            print(f'    - "{t.name}"  ({len(assets_using)} assets)')
            for a in assets_using:
                AssetEvent.objects(asset=a).delete()
                a.delete()
                print(f'        deleted asset: {a.serial_number}')
            t.delete()
            print(f'      deleted type.')

    # ── 3. Clean up assets with null/missing asset_type ────────────────────────
    orphans = list(Asset.objects(__raw__={'asset_type_id': None}))
    orphans += list(Asset.objects(__raw__={'asset_type_id': {'$exists': False}}))
    if orphans:
        print(f'\n  Assets with no type ({len(orphans)}):')
        for a in orphans:
            print(f'    - {a.serial_number} (keeping, type=None)')
    else:
        print('\n  No orphaned assets found.')

    print('\nMigration complete.')
    final = list(AssetType.objects.order_by('name'))
    print(f'Active categories ({len(final)}):')
    for t in final:
        cnt = Asset.objects(asset_type=t).count()
        print(f'  {t.name}  ({cnt} assets)')
