# seed_inventory.py
# Run once to populate the database with hardware inventory models.
# Usage: python seed_inventory.py

from app import create_app, db
from app.models.asset import Asset, AssetType
from app.models.site import Site

app = create_app()

INVENTORY = [
    # Routers
    dict(serial_number='C8300-1N1S-4T2X',       model='C8300-1N1S-4T2X',       asset_type='Router',        manufacturer='Cisco'),
    dict(serial_number='C8500L-8S4X',            model='C8500L-8S4X',            asset_type='Router',        manufacturer='Cisco'),
    dict(serial_number='C1111X-8P',              model='C1111X-8P',              asset_type='Router',        manufacturer='Cisco'),
    dict(serial_number='C1161X-8P',              model='C1161X-8P',              asset_type='Router',        manufacturer='Cisco'),
    dict(serial_number='ASR1001-X',              model='ASR1001-X',              asset_type='Router',        manufacturer='Cisco'),
    dict(serial_number='ASR1001-HX',             model='ASR1001-HX',             asset_type='Router',        manufacturer='Cisco'),
    dict(serial_number='ISR 4331AX/K9',          model='ISR 4331AX/K9',          asset_type='Router',        manufacturer='Cisco'),
    dict(serial_number='ISR 4331-DC/K9',         model='ISR 4331-DC/K9',         asset_type='Router',        manufacturer='Cisco'),
    dict(serial_number='ISR 4321',               model='ISR 4321',               asset_type='Router',        manufacturer='Cisco'),
    dict(serial_number='ASR-1009X',              model='ASR-1009X',              asset_type='Router',        manufacturer='Cisco'),
    dict(serial_number='NB-VC-3400-P-RTR-C',    model='NB-VC-3400-P-RTR-C',    asset_type='Router',        manufacturer='Cisco'),
    # Switches
    dict(serial_number='C9300-24S-A',            model='C9300-24S-A',            asset_type='Switch',        manufacturer='Cisco'),
    dict(serial_number='C9300-48S-A',            model='C9300-48S-A',            asset_type='Switch',        manufacturer='Cisco'),
    dict(serial_number='C9500-24Y4C-A',          model='C9500-24Y4C-A',          asset_type='Switch',        manufacturer='Cisco'),
    dict(serial_number='C9500-48Y4C-A',          model='C9500-48Y4C-A',          asset_type='Switch',        manufacturer='Cisco'),
    dict(serial_number='C9300X-12Y-A',           model='C9300X-12Y-A',           asset_type='Switch',        manufacturer='Cisco'),
    dict(serial_number='C9300-24P-A',            model='C9300-24P-A',            asset_type='Switch',        manufacturer='Cisco'),
    dict(serial_number='C9300-48P-A',            model='C9300-48P-A',            asset_type='Switch',        manufacturer='Cisco'),
    dict(serial_number='C9200CX-12P-2X2G-A',    model='C9200CX-12P-2X2G-A',    asset_type='Switch',        manufacturer='Cisco'),
    dict(serial_number='MS-390-48-HW',           model='MS-390-48-HW',           asset_type='Switch',        manufacturer='Cisco Meraki'),
    # SFP Modules
    dict(serial_number='GLC-LH-SMD',            model='GLC-LH-SMD',             asset_type='SFP Module',    manufacturer='Cisco'),
    dict(serial_number='SFP-1G-LH',             model='SFP-1G-LH',              asset_type='SFP Module',    manufacturer='Cisco'),
    dict(serial_number='GLC-SX-MMD',            model='GLC-SX-MMD',             asset_type='SFP Module',    manufacturer='Cisco'),
    dict(serial_number='GLC-SX-MM',             model='GLC-SX-MM',              asset_type='SFP Module',    manufacturer='Cisco'),
    dict(serial_number='SFP-10G-LR-S',          model='SFP-10G-LR-S',           asset_type='SFP Module',    manufacturer='Cisco'),
    dict(serial_number='SFP-10G-SR-S',          model='SFP-10G-SR-S',           asset_type='SFP Module',    manufacturer='Cisco'),
    dict(serial_number='SFP-10G-SR',            model='SFP-10G-SR',             asset_type='SFP Module',    manufacturer='Cisco'),
    dict(serial_number='GLC-BX-D',              model='GLC-BX-D',               asset_type='SFP Module',    manufacturer='Cisco'),
    dict(serial_number='GLC-BX-U',              model='GLC-BX-U',               asset_type='SFP Module',    manufacturer='Cisco'),
    dict(serial_number='GLC-TE',                model='GLC-TE',                 asset_type='SFP Module',    manufacturer='Cisco'),
    dict(serial_number='SFP-1G-T-X',            model='SFP-1G-T-X',             asset_type='SFP Module',    manufacturer='Cisco'),
    dict(serial_number='SFP-10G-T-X',           model='SFP-10G-T-X',            asset_type='SFP Module',    manufacturer='Cisco'),
    # Cards & Modules
    dict(serial_number='C-NIM-4X',              model='C-NIM-4X',               asset_type='Card / Module', manufacturer='Cisco'),
    dict(serial_number='C-NIM-1X',              model='C-NIM-1X',               asset_type='Card / Module', manufacturer='Cisco'),
    dict(serial_number='C-NIM-2T',              model='C-NIM-2T',               asset_type='Card / Module', manufacturer='Cisco'),
    dict(serial_number='C-NIM-SM-ADPT',         model='C-NIM-SM-ADPT',          asset_type='Card / Module', manufacturer='Cisco'),
    dict(serial_number='ASR-MIP100',            model='ASR-MIP100',             asset_type='Card / Module', manufacturer='Cisco'),
    dict(serial_number='EPA 10X10GE',           model='EPA 10X10GE',            asset_type='Card / Module', manufacturer='Cisco'),
    dict(serial_number='EPA 18X1GE',            model='EPA 18X1GE',             asset_type='Card / Module', manufacturer='Cisco'),
    dict(serial_number='NIM-2GE-CU-SFP',       model='NIM-2GE-CU-SFP',         asset_type='Card / Module', manufacturer='Cisco'),
    # Power Supplies
    dict(serial_number='PWR-C1-715WAC-P',       model='PWR-C1-715WAC-P',        asset_type='Power Supply',  manufacturer='Cisco'),
    dict(serial_number='PWR-C1-715WDC-P',       model='PWR-C1-715WDC-P',        asset_type='Power Supply',  manufacturer='Cisco'),
    # Cables
    dict(serial_number='CAB-48DC-40A-8AWG',     model='CAB-48DC-40A-8AWG',      asset_type='Cable',         manufacturer='Cisco'),
    dict(serial_number='CAB-CONSOLE-USBRJ45',   model='CAB-CONSOLE-USBRJ45',    asset_type='Cable',         manufacturer='Cisco'),
    dict(serial_number='CAB-CONSOLE-RJ45',      model='CAB-CONSOLE-RJ45',       asset_type='Cable',         manufacturer='Cisco'),
    dict(serial_number='CISCO USB A TO MINI B', model='CISCO USB A TO MINI B',  asset_type='Cable',         manufacturer='Cisco'),
]

ASSET_TYPE_CATEGORIES = {
    'Router':        'Networking',
    'Switch':        'Networking',
    'SFP Module':    'Networking',
    'Card / Module': 'Networking',
    'Power Supply':  'Power',
    'Cable':         'Cabling',
}

with app.app_context():
    db.create_all()

    site = Site.query.filter_by(name='Kodkod Base').first()
    if not site:
        site = Site(name='Kodkod Base')
        db.session.add(site)
        db.session.flush()
        print('  Created site: Kodkod Base')

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
