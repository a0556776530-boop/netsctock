"""
fetch_asset_photos.py
---------------------
Fetches accurate product images using Serper image search.
Searches with exact model number in quotes, filters logos,
prefers trusted sources (cisco.com, cdw.com, amazon.com).
Saves base64 JPEG to MongoDB.

Usage:
    pip install Pillow requests
    python fetch_asset_photos.py
"""

import base64
import io
import json
import os
import re
import time

import requests
from bs4 import BeautifulSoup
from PIL import Image
from mongoengine import connect
from dotenv import load_dotenv

load_dotenv()

MONGO_URI      = os.environ['MONGO_URI']
SERPER_API_KEY = 'b34037cc391417f941c8b5eef49318a4119d9fa0'
TARGET_W       = 400
TARGET_H       = 300
JPEG_QUALITY   = 85
PAUSE          = 1.2

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                  'AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
}

# Sources we trust for accurate product images
TRUSTED_SOURCES = ['cisco.com', 'cdw.com', 'amazon.com', 'newegg.com',
                   'bhphotovideo.com', 'provantage.com', 'networkcraze.com']

# Skip image URLs that look like logos/icons
LOGO_KEYWORDS = ['logo', 'icon', 'favicon', 'badge', 'banner', 'avatar',
                 'sprite', 'placeholder', 'blank', 'default']


def _resize(img_bytes: bytes) -> str:
    img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
    img.thumbnail((TARGET_W, TARGET_H), Image.LANCZOS)
    canvas = Image.new('RGB', (TARGET_W, TARGET_H), (255, 255, 255))
    x = (TARGET_W - img.width) // 2
    y = (TARGET_H - img.height) // 2
    canvas.paste(img, (x, y))
    buf = io.BytesIO()
    canvas.save(buf, format='JPEG', quality=JPEG_QUALITY)
    return f'data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}'


def _download(url: str) -> bytes | None:
    try:
        r = requests.get(url, timeout=12, headers=HEADERS)
        if r.status_code == 200 and len(r.content) > 5000:
            return r.content
    except Exception:
        pass
    return None


def _is_bad_url(url: str) -> bool:
    low = url.lower()
    return any(kw in low for kw in LOGO_KEYWORDS)


def _serper_images(query: str, num: int = 10) -> list[dict]:
    """Return image results from Serper image search."""
    try:
        resp = requests.post(
            'https://google.serper.dev/images',
            headers={'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'},
            data=json.dumps({'q': query, 'num': num}),
            timeout=10,
        )
        return resp.json().get('images', [])
    except Exception as e:
        print(f'    Serper error: {e}')
        return []


def _best_image(results: list[dict]) -> bytes | None:
    """Pick the best image from results — trusted sources first, then others."""
    trusted = []
    others  = []
    for item in results:
        url = item.get('imageUrl', '')
        if not url or _is_bad_url(url):
            continue
        if any(src in url for src in TRUSTED_SOURCES):
            trusted.append(url)
        else:
            others.append(url)

    for url in trusted + others:
        img = _download(url)
        if img:
            print(f'    source: {url[:80]}')
            return img
    return None


def _serper_web(query: str, num: int = 5) -> list[str]:
    """Return top page URLs from Serper web search."""
    try:
        resp = requests.post(
            'https://google.serper.dev/search',
            headers={'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'},
            data=json.dumps({'q': query, 'num': num}),
            timeout=10,
        )
        items = resp.json().get('organic', [])
        return [item['link'] for item in items if item.get('link')]
    except Exception:
        return []


def _parse_spec_table(soup) -> dict:
    """Parse Cisco spec table — reads label/value pairs from <table> and <dl> elements."""
    specs = {}
    rows  = []

    # Collect all label→value pairs from tables
    for table in soup.find_all('table'):
        for tr in table.find_all('tr'):
            cells = tr.find_all(['th', 'td'])
            if len(cells) >= 2:
                label = cells[0].get_text(' ', strip=True).lower()
                value = cells[1].get_text(' ', strip=True)
                rows.append((label, value))

    # Also collect from definition lists
    for dl in soup.find_all('dl'):
        for dt, dd in zip(dl.find_all('dt'), dl.find_all('dd')):
            rows.append((dt.get_text(' ', strip=True).lower(),
                         dd.get_text(' ', strip=True)))

    for label, value in rows:
        val_low = value.lower()

        # ── RJ45 ports ──────────────────────────────────────────────────────
        if any(k in label for k in ['ethernet port', 'copper port', 'rj-45', 'rj45',
                                     '10/100/1000', 'gigabit ethernet port', 'lan port']):
            m = re.search(r'(\d+)', value)
            if m and 'rj45_ports' not in specs:
                specs['rj45_ports'] = int(m.group(1))

        # ── SFP ports ───────────────────────────────────────────────────────
        if any(k in label for k in ['sfp', 'fiber port', 'uplink port',
                                     'optical port', 'expansion module']):
            m = re.search(r'(\d+)', value)
            if m and 'sfp_ports' not in specs:
                specs['sfp_ports'] = int(m.group(1))

        # ── PoE ─────────────────────────────────────────────────────────────
        if 'poe' in label or 'power over ethernet' in label:
            if 'poe+' in val_low or 'poe plus' in val_low:
                specs['poe'] = 'PoE+'
            elif 'poe' in val_low or 'yes' in val_low or 'supported' in val_low:
                specs['poe'] = 'PoE'

        # ── Power consumption ────────────────────────────────────────────────
        if any(k in label for k in ['power consumption', 'maximum power',
                                     'typical power', 'power draw', 'power supply']):
            m = re.search(r'(\d+(?:\.\d+)?)\s*w\b', value, re.I)
            if m and 'power_watts' not in specs:
                specs['power_watts'] = float(m.group(1))

        # ── Rack units ───────────────────────────────────────────────────────
        if any(k in label for k in ['rack unit', 'form factor', 'height']):
            m = re.search(r'(\d+(?:\.\d+)?)\s*u\b', val_low)
            if m and 'rack_units' not in specs:
                specs['rack_units'] = float(m.group(1))
            elif re.search(r'\b1u\b', val_low):
                specs.setdefault('rack_units', 1.0)
            elif re.search(r'\b2u\b', val_low):
                specs.setdefault('rack_units', 2.0)

        # ── Depth ────────────────────────────────────────────────────────────
        if any(k in label for k in ['dimension', 'depth']):
            # Cisco often writes dimensions as "W x D x H in / mm"
            # Try to grab the second number (D) from "W x D x H"
            parts = re.findall(r'(\d+(?:\.\d+)?)', value)
            unit_m = re.search(r'(mm|cm|in)', value, re.I)
            unit = unit_m.group(1).lower() if unit_m else 'mm'
            if len(parts) >= 2 and 'depth_mm' not in specs:
                val = float(parts[1])  # second dimension = depth
                if unit == 'cm':
                    val = round(val * 10)
                elif unit == 'in':
                    val = round(val * 25.4)
                specs['depth_mm'] = int(val)

    return specs


def _fetch_specs(model: str, manufacturer: str) -> dict:
    """Fetch technical specs by parsing the Cisco product page spec table."""
    if not model:
        return {}

    # Search for the product page and also the datasheet page
    queries = [
        f'"{model}" specifications site:cisco.com',
        f'"{model}" datasheet site:cisco.com',
    ]

    for query in queries:
        urls = _serper_web(query, num=5)
        for url in urls:
            if 'cisco.com' not in url:
                continue
            # Skip community / forum pages
            if any(x in url for x in ['community.cisco.com', '/t5/', '/forum']):
                continue
            try:
                r = requests.get(url, timeout=12, headers=HEADERS)
                if r.status_code != 200:
                    continue
                soup  = BeautifulSoup(r.text, 'html.parser')
                specs = _parse_spec_table(soup)
                if specs:
                    print(f'    specs from: {url[:80]}')
                    return specs
            except Exception:
                continue

    return {}


def _fetch_for_asset(model: str, manufacturer: str) -> bytes | None:
    queries = []

    if model:
        # Exact model in quotes — most precise
        queries.append(f'"{model}" product image')
        queries.append(f'"{model}" {manufacturer}')

    for query in queries:
        print(f'    query: {query}')
        results = _serper_images(query)
        img = _best_image(results)
        if img:
            return img

    return None


def main():
    connect(host=MONGO_URI, db='netstock')
    from app.models.asset import Asset

    assets = list(Asset.objects())
    total  = len(assets)
    print(f'Fetching specs for {total} assets.\n')

    ok = fail = 0

    for i, asset in enumerate(assets, 1):
        model = (asset.model or '').strip()
        mfr   = (asset.manufacturer or '').strip()
        sn    = (asset.serial_number or '').strip()
        label = model or sn or f'asset#{i}'

        print(f'[{i}/{total}] {label}')

        search_term = model or sn
        specs = _fetch_specs(search_term, mfr)

        if specs:
            try:
                asset.specs = specs
                asset.save()
                print(f'    ✓ specs: {specs}')
                ok += 1
            except Exception as e:
                print(f'    ✗ error: {e}')
                fail += 1
        else:
            print(f'    ✗ no specs found')
            fail += 1

        time.sleep(PAUSE)

    print(f'\nDone. ✓ {ok}  ✗ {fail}  (total {total})')


if __name__ == '__main__':
    main()
