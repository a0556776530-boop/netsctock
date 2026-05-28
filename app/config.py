import os
import secrets
from dotenv import load_dotenv

load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))

MONGO_URI = os.environ.get('MONGO_URI', '')


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)

    MONGODB_SETTINGS = {
        'host': MONGO_URI,
        'db':   'netstock',
    }

    # Session cookie security
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_DURATION = 60 * 60 * 24 * 14  # 14 days

    WTF_CSRF_TIME_LIMIT = 3600  # 1 hour
    TEMPLATES_AUTO_RELOAD = True

    CISCO_SERIAL_PATTERN = r'^[A-Z]{3}[0-9]{4}[A-Z0-9]{4}$'
