# seed_inventory.py
# Run once to populate the database with hardware inventory models.
# Usage: python seed_inventory.py

from app import create_app, db
from app.models.asset import Asset, AssetType
from app.models.site import Site

app = create_app()

INVENTORY = [
    # Routers
    dict(serial_number='C8300-1N1S-4T2X',       model='C8300-1N1S-4T2X',       asset_type='Router',         manufacturer='Cisco'),
    dict(serial_number='C8500L-8S4X',            model='C8500L-8S4X',            asset_type='Router',         manufacturer='Cisco'),
    dict(serial_number='C1111X-8P',              model='C1111X-8P',              asset_type='Router',         manufacturer='Cisco'),
    dict(serial_number='C1161X-8P',              model='C1161X-8P',              asset_type='Router',         manufacturer='Cisco'),
    dict(serial_number='ASR1001-X',              model='ASR1001-X',              asset_type='Router',         manufacturer='Cisco'),
    dict(serial_number='ASR1001-HX',             model='ASR1001-HX',             asset_type='Router',         manufacturer='Cisco'),
    dict(serial_number='ISR 4331AX/K9',          model='ISR 4331AX/K9',          asset_type='Router',         manufacturer='Cisco'),
    dict(serial_number='ISR 4331-DC/K9',         model='ISR 4331-DC/K9',         asset_type='Router',         manufacturer='Cisco'),
    dict(serial_number='ISR 4321',               model='ISR 4321',               asset_type='Router',         manufacturer='Cisco'),
    dict(serial_number='ASR-1009X',              model='ASR-1009X',              asset_type='Router',         manufacturer='Cisco'),
    dict(serial_number='NB-VC-3400-P-RTR-C',    model='NB-VC-3400-P-RTR-C',    asset_type='Router',         manufacturer='Dell'),
    # Aggregation Switches
    dict(serial_number='C9300-24S-A',            model='C9300-24S-A',            asset_type='Aggregation',    manufacturer='Cisco'),
    dict(serial_number='C9300-48S-A',            model='C9300-48S-A',            asset_type='Aggregation',    manufacturer='Cisco'),
    dict(serial_number='C9500-24Y4C-A',          model='C9500-24Y4C-A',          asset_type='Aggregation',    manufacturer='Cisco'),
    dict(serial_number='C9500-48Y4C-A',          model='C9500-48Y4C-A',          asset_type='Aggregation',    manufacturer='Cisco'),
    dict(serial_number='C9300X-12Y-A',           model='C9300X-12Y-A',           asset_type='Aggregation',    manufacturer='Cisco'),
    # Access Switches
    dict(serial_number='C9300-24P-A',            model='C9300-24P-A',            asset_type='Access Switch',  manufacturer='Cisco'),
    dict(serial_number='C9300-48P-A',            model='C9300-48P-A',            asset_type='Access Switch',  manufacturer='Cisco'),
    dict(serial_number='C9200CX-12P-2X2G-A',    model='C9200CX-12P-2X2G-A',    asset_type='Access Switch',  manufacturer='Cisco'),
    dict(serial_number='MS-390-48-HW',           model='MS-390-48-HW',           asset_type='Access Switch',  manufacturer='Cisco Meraki'),
    dict(serial_number='C1100TG-1N24P32A',       model='C1100TG-1N24P32A',       asset_type='Access Switch',  manufacturer='Cisco'),
    # SFP Modules
    dict(serial_number='GLC-LH-SMD',            model='GLC-LH-SMD',             asset_type='SFP',            manufacturer='Cisco'),
    dict(serial_number='SFP-1G-LH',             model='SFP-1G-LH',              asset_type='SFP',            manufacturer='Cisco'),
    dict(serial_number='GLC-SX-MMD',            model='GLC-SX-MMD',             asset_type='SFP',            manufacturer='Cisco'),
    dict(serial_number='GLC-SX-MM',             model='GLC-SX-MM',              asset_type='SFP',            manufacturer='Cisco'),
    dict(serial_number='SFP-10G-LR-S',          model='SFP-10G-LR-S',           asset_type='SFP',            manufacturer='Cisco'),
    dict(serial_number='SFP-10G-SR-S',          model='SFP-10G-SR-S',           asset_type='SFP',            manufacturer='Cisco'),
    dict(serial_number='SFP-10G-SR',            model='SFP-10G-SR',             asset_type='SFP',            manufacturer='Cisco'),
    dict(serial_number='GLC-BX-D',              model='GLC-BX-D',               asset_type='SFP',            manufacturer='Cisco'),
    dict(serial_number='GLC-BX-U',              model='GLC-BX-U',               asset_type='SFP',            manufacturer='Cisco'),
    dict(serial_number='GLC-TE',                model='GLC-TE',                 asset_type='SFP',            manufacturer='Cisco'),
    dict(serial_number='SFP-1G-T-X',            model='SFP-1G-T-X',             asset_type='SFP',            manufacturer='Cisco'),
    dict(serial_number='SFP-10G-T-X',           model='SFP-10G-T-X',            asset_type='SFP',            manufacturer='Cisco'),
    # Cards & Modules
    dict(serial_number='C-NIM-4X',              model='C-NIM-4X',               asset_type='Cards',          manufacturer='Cisco'),
    dict(serial_number='C-NIM-1X',              model='C-NIM-1X',               asset_type='Cards',          manufacturer='Cisco'),
    dict(serial_number='C-NIM-2T',              model='C-NIM-2T',               asset_type='Cards',          manufacturer='Cisco'),
    dict(serial_number='C-NIM-SM-ADPT',         model='C-NIM-SM-ADPT',          asset_type='Cards',          manufacturer='Cisco'),
    dict(serial_number='ASR-MIP100',            model='ASR-MIP100',             asset_type='Cards',          manufacturer='Cisco'),
    dict(serial_number='EPA 10X10GE',           model='EPA 10X10GE',            asset_type='Cards',          manufacturer='Cisco'),
    dict(serial_number='EPA 18X1GE',            model='EPA 18X1GE',             asset_type='Cards',          manufacturer='Cisco'),
    dict(serial_number='SPA 8X1GE',             model='SPA 8X1GE',              asset_type='Cards',          manufacturer='Cisco'),
    dict(serial_number='NIM-2GE-CU-SFP',        model='NIM-2GE-CU-SFP',         asset_type='Cards',          manufacturer='Cisco'),
    dict(serial_number='MA-MOD-8X10G',          model='MA-MOD-8X10G',           asset_type='Cards',          manufacturer='Cisco Meraki'),
    dict(serial_number='C9300-NM-8X',           model='C9300-NM-8X',            asset_type='Cards',          manufacturer='Cisco'),
    # Power Supplies
    dict(serial_number='PWR-C1-715WAC-P',       model='PWR-C1-715WAC-P',        asset_type='Power Supply',   manufacturer='Cisco'),
    dict(serial_number='PWR-C1-715WDC-P',       model='PWR-C1-715WDC-P',        asset_type='Power Supply',   manufacturer='Cisco'),
    dict(serial_number='C9K-PWR-930WDC-R',      model='C9K-PWR-930WDC-R',       asset_type='Power Supply',   manufacturer='Cisco'),
    dict(serial_number='PWR-CC1-400WDC',        model='PWR-CC1-400WDC',         asset_type='Power Supply',   manufacturer='Cisco'),
    dict(serial_number='MA-PWR-350WAC',         model='MA-PWR-350WAC',          asset_type='Power Supply',   manufacturer='Cisco Meraki'),
    # Power Cords
    dict(serial_number='CAB-48DC-40A-8AWG',     model='CAB-48DC-40A-8AWG',      asset_type='Power Cords',    manufacturer='Cisco'),
    dict(serial_number='CAB-C15-CBN',           model='CAB-C15-CBN',            asset_type='Power Cords',    manufacturer='Cisco'),
    dict(serial_number='CAB-C19-CBN',           model='CAB-C19-CBN',            asset_type='Power Cords',    manufacturer='Cisco'),
    dict(serial_number='CAB-TA-IS',             model='CAB-TA-IS',              asset_type='Power Cords',    manufacturer='Cisco'),
    dict(serial_number='CAB-C15-ISR',           model='CAB-C15-ISR',            asset_type='Power Cords',    manufacturer='Cisco'),
    dict(serial_number='CAB-C13-CBN',           model='CAB-C13-CBN',            asset_type='Power Cords',    manufacturer='Cisco'),
    dict(serial_number='CAB-C13-C14-2M',        model='CAB-C13-C14-2M',         asset_type='Power Cords',    manufacturer='Cisco'),
    dict(serial_number='CAB-TA-EU',             model='CAB-TA-EU',              asset_type='Power Cords',    manufacturer='Cisco'),
    dict(serial_number='PWR-CAB-AC-BLK',        model='PWR-CAB-AC-BLK',         asset_type='Power Cords',    manufacturer='Cisco'),
    # Console Cables
    dict(serial_number='CAB-CONSOLE-USBRJ45',   model='CAB-CONSOLE-USBRJ45',    asset_type='Console Cables', manufacturer='Cisco'),
    dict(serial_number='CAB-CONSOLE-RJ45',      model='CAB-CONSOLE-RJ45',       asset_type='Console Cables', manufacturer='Cisco'),
    dict(serial_number='CAB-CONSOLE-USB',       model='CAB-CONSOLE-USB',        asset_type='Console Cables', manufacturer='Cisco'),
]

ASSET_TYPE_CATEGORIES = {
    'Router':         'Networking',
    'Aggregation':    'Networking',
    'Access Switch':  'Networking',
    'SFP':            'Networking',
    'Cards':          'Networking',
    'Power Supply':   'Power',
    'Power Cords':    'Power',
    'Console Cables': 'Cabling',
}

with app.app_context():
    db.create_all()

    site = Site.query.filter_by(name='Kodkod Base').first()
    if not site:
        site = Site(name='Kodkod Base')
        db.session.add(site)
        db.session.flush()
        print('  Created site: Kodkod Base')

    # Fix manufacturer for NB-VC-3400-P-RTR-C (Dell, not Cisco)
    nb_asset = Asset.query.filter_by(serial_number='NB-VC-3400-P-RTR-C').first()
    if nb_asset and nb_asset.manufacturer != 'Dell':
        nb_asset.manufacturer = 'Dell'
        print('  Updated manufacturer: NB-VC-3400-P-RTR-C -> Dell')

    inserted = 0
    skipped = 0

    for item in INVENTORY:
        asset_type = AssetType.query.filter_by(name=item['asset_type']).first()
        if not asset_type:
            category = ASSET_TYPE_CATEGORIES.get(item['asset_type'], 'Networking')
            asset_type = AssetType(name=item['asset_type'], category=category)
            db.session.add(asset_type)
            db.session.flush()
            print(f"  Created asset type: {item['asset_type']}")

        if Asset.query.filter_by(serial_number=item['serial_number']).first():
            print(f"  Skipped (exists): {item['serial_number']}")
            skipped += 1
            continue

        asset = Asset(
            serial_number=item['serial_number'],
            model=item['model'],
            manufacturer=item['manufacturer'],
            asset_type_id=asset_type.id,
            current_site_id=site.id,
            status='in_storage',
        )
        db.session.add(asset)
        print(f"  Inserted: {item['serial_number']} ({item['asset_type']})")
        inserted += 1

    db.session.commit()
    print(f'\nDone. Inserted: {inserted}, Skipped: {skipped}')
