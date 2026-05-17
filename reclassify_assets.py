# reclassify_assets.py
# One-time script to restructure asset types to match the physical inventory groupings.
# Usage: python reclassify_assets.py

from app import create_app, db
from app.models.asset import Asset, AssetType

app = create_app()

AGGREGATION_SERIALS = {
    'C9300-24S-A', 'C9300-48S-A', 'C9500-24Y4C-A', 'C9500-48Y4C-A', 'C9300X-12Y-A',
}
ACCESS_SWITCH_SERIALS = {
    'C9300-24P-A', 'C9300-48P-A', 'C9200CX-12P-2X2G-A', 'MS-390-48-HW', 'C1100TG-1N24P32A',
}
POWER_CORD_SERIALS = {
    'CAB-48DC-40A-8AWG', 'CAB-C15-CBN', 'CAB-C19-CBN', 'CAB-TA-IS', 'CAB-C15-ISR',
    'CAB-C13-CBN', 'CAB-C13-C14-2M', 'CAB-TA-EU', 'PWR-CAB-AC-BLK',
}
CONSOLE_CABLE_SERIALS = {
    'CAB-CONSOLE-USBRJ45', 'CAB-CONSOLE-RJ45', 'CAB-CONSOLE-USB',
}


def get_or_create_type(name, category):
    t = AssetType.query.filter_by(name=name).first()
    if not t:
        t = AssetType(name=name, category=category)
        db.session.add(t)
        db.session.flush()
        print(f'  Created type: {name}')
    return t


with app.app_context():
    # ── Renames ──────────────────────────────────────────────────────────────
    sfp_type = AssetType.query.filter_by(name='SFP Module').first()
    if sfp_type:
        sfp_type.name = 'SFP'
        print('  Renamed: SFP Module -> SFP')

    card_type = AssetType.query.filter_by(name='Card / Module').first()
    if card_type:
        card_type.name = 'Cards'
        print('  Renamed: Card / Module -> Cards')

    db.session.flush()

    # ── New types ─────────────────────────────────────────────────────────────
    aggregation_type   = get_or_create_type('Aggregation',    'Networking')
    access_type        = get_or_create_type('Access Switch',  'Networking')
    power_cords_type   = get_or_create_type('Power Cords',    'Power')
    console_cable_type = get_or_create_type('Console Cables', 'Cabling')

    # ── Reassign assets ───────────────────────────────────────────────────────
    for serial in AGGREGATION_SERIALS:
        asset = Asset.query.filter_by(serial_number=serial).first()
        if asset:
            asset.asset_type_id = aggregation_type.id
            print(f'  Aggregation   <- {serial}')

    for serial in ACCESS_SWITCH_SERIALS:
        asset = Asset.query.filter_by(serial_number=serial).first()
        if asset:
            asset.asset_type_id = access_type.id
            print(f'  Access Switch <- {serial}')

    for serial in POWER_CORD_SERIALS:
        asset = Asset.query.filter_by(serial_number=serial).first()
        if asset:
            asset.asset_type_id = power_cords_type.id
            print(f'  Power Cords   <- {serial}')

    for serial in CONSOLE_CABLE_SERIALS:
        asset = Asset.query.filter_by(serial_number=serial).first()
        if asset:
            asset.asset_type_id = console_cable_type.id
            print(f'  Console Cables<- {serial}')

    # ── Remove now-empty legacy types ─────────────────────────────────────────
    for old_name in ('Switch', 'Cable'):
        old_type = AssetType.query.filter_by(name=old_name).first()
        if old_type:
            remaining = Asset.query.filter_by(asset_type_id=old_type.id).count()
            if remaining == 0:
                db.session.delete(old_type)
                print(f'  Deleted empty type: {old_name}')
            else:
                print(f'  WARNING: "{old_name}" still has {remaining} asset(s) — skipped deletion')

    db.session.commit()
    print('\nDone.')
