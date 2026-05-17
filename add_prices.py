# add_prices.py
# Adds price columns to the DB and populates them with realistic random prices.
# Usage: python add_prices.py

import sqlite3
import random
from app import create_app, db
from app.models.asset import Asset

app = create_app()

NIS_PER_USD = 3.65

PRICE_RANGES_USD = {
    'Router':         (3_000,  80_000),
    'Aggregation':    (15_000, 120_000),
    'Access Switch':  (2_000,  25_000),
    'SFP':            (80,     3_500),
    'Cards':          (800,    20_000),
    'Power Supply':   (400,    4_000),
    'Power Cords':    (30,     400),
    'Console Cables': (25,     120),
}

# ── Add columns if they don't exist yet ──────────────────────────────────────
with sqlite3.connect('netstock.db') as conn:
    existing = {row[1] for row in conn.execute('PRAGMA table_info(assets)')}
    for col in ('price', 'price_nis', 'price_usd'):
        if col not in existing:
            conn.execute(f'ALTER TABLE assets ADD COLUMN {col} REAL')
            print(f'  Added column: {col}')
        else:
            print(f'  Column already exists: {col}')

# ── Populate prices via ORM ───────────────────────────────────────────────────
with app.app_context():
    assets = Asset.query.all()
    for asset in assets:
        type_name = asset.asset_type.name if asset.asset_type else 'Other'
        lo, hi = PRICE_RANGES_USD.get(type_name, (500, 10_000))
        list_price = round(random.uniform(lo, hi))
        asset.price     = list_price
        asset.price_usd = round(list_price * random.uniform(0.82, 0.96))
        asset.price_nis = round(list_price * NIS_PER_USD * random.uniform(0.97, 1.03))

    db.session.commit()
    print(f'\nPrices set for {len(assets)} assets.')
