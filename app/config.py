import os
from dotenv import load_dotenv

load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))

MONGO_URI = os.environ.get('MONGO_URI', '')


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

    MONGODB_SETTINGS = {
        'host': MONGO_URI,
        'db':   'netstock',
    }

    CISCO_SERIAL_PATTERN = r'^[A-Z]{3}[0-9]{4}[A-Z0-9]{4}$'
