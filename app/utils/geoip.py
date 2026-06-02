"""
Offline GeoIP lookup using a local MaxMind GeoLite2-City.mmdb database.

The database file must be placed at:  <project_root>/data/GeoLite2-City.mmdb

To download (free, requires MaxMind account):
  https://www.maxmind.com/en/geolite2/signup
  Then: GeoLite2 City → Download GZIP → extract GeoLite2-City.mmdb → place in data/

For Render: add to Build Command:
  pip install -r requirements.txt && \
  mkdir -p data && \
  curl -sL "https://download.maxmind.com/app/geoip_download?edition_id=GeoLite2-City&license_key=$MAXMIND_KEY&suffix=tar.gz" \
    | tar -xz --strip-components=1 -C data --wildcards "*.mmdb"
"""

import ipaddress
import os

_DB_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'GeoLite2-City.mmdb')
)
_reader = None


def _get_reader():
    global _reader
    if _reader is not None:
        return _reader
    if not os.path.exists(_DB_PATH):
        return None
    try:
        import geoip2.database
        _reader = geoip2.database.Reader(_DB_PATH)
        return _reader
    except Exception:
        return None


def _is_private(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_private
    except ValueError:
        return False


def get_real_ip(request) -> str:
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or '0.0.0.0'


def lookup(ip: str) -> tuple[str, str]:
    """Return (city, country). Never raises. No internet needed at runtime."""
    if not ip or ip in ('127.0.0.1', '::1') or _is_private(ip):
        return 'רשת פנימית', '—'

    reader = _get_reader()
    if reader is None:
        return '—', '—'

    try:
        resp = reader.city(ip)
        city    = resp.city.name    or '—'
        country = resp.country.name or '—'
        return city, country
    except Exception:
        return '—', '—'
