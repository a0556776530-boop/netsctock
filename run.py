"""
Development entry point.

Usage:
    python run.py

The database is created automatically on first run.
Default login: admin@inventory.app / admin1234
"""
import os

if 'DATABASE_URL' not in os.environ:
    _here = os.path.dirname(os.path.abspath(__file__))
    os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(_here, 'inventory.db')

from app import create_app, db

app = create_app()

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
