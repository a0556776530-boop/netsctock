import os
import secrets
from dotenv import load_dotenv

load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))

MONGO_URI = os.environ.get('MONGO_URI', '')

# Secure cookies require HTTPS. Disable only when running the dev server locally.
_HTTPS = os.environ.get('FLASK_DEBUG', '0') != '1'


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)

    MONGODB_SETTINGS = {
        'host': MONGO_URI,
        'db':   'netstock',
    }

    # Session cookie security
    SESSION_COOKIE_HTTPONLY  = True
    SESSION_COOKIE_SAMESITE  = 'Lax'
    SESSION_COOKIE_SECURE    = _HTTPS
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE   = _HTTPS
    REMEMBER_COOKIE_DURATION = 60 * 60 * 24 * 14  # 14 days

    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50 MB upload limit
    WTF_CSRF_TIME_LIMIT = 3600  # 1 hour
    TEMPLATES_AUTO_RELOAD = True

    CISCO_SERIAL_PATTERN = r'^[A-Z]{3}[0-9]{4}[A-Z0-9]{4}$'
