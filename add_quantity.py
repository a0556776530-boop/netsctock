# add_quantity.py
# Adds the quantity column to the DB and seeds random stock values.
# Usage: python add_quantity.py

import sqlite3
import random
from app import create_app, db
from app.models.asset import Asset

app = create_app()

QUANTITY_RANGES = {
    'Router':         (1, 10),
    'Aggregation':    (1, 8),
    'Access Switch':  (2, 10),
    'SFP':            (3, 25),
    'Cards':          (2, 12),
    'Power Supply':   (2, 10),
    'Power Cords':    (4, 20),
    'Console Cables': (4, 15),
}

# ── Add column if missing ─────────────────────────────────────────────────────
with sqlite3.connect('netstock.db') as conn:
    existing = {row[1] for row in conn.execute('PRAGMA table_info(assets)')}
    if 'quantity' not in existing:
        conn.execute('ALTER TABLE assets ADD COLUMN quantity INTEGER')
        print('  Added column: quantity')
    else:
        print('  Column already exists: quantity')

# ── Populate quantities ───────────────────────────────────────────────────────
with app.app_context():
    assets = Asset.query.all()
    for asset in assets:
        type_name = asset.asset_type.name if asset.asset_type else 'Other'
        lo, hi = QUANTITY_RANGES.get(type_name, (1, 10))
        asset.quantity = random.randint(lo, hi)
    db.session.commit()
    low_stock = sum(1 for a in assets if a.quantity is not None and a.quantity < 5)
    print(f'  Quantities set for {len(assets)} assets.')
    print(f'  {low_stock} item(s) below alert threshold (qty < 5).')
