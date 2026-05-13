# seed_inventory.py
# Run once to populate the database with initial inventory data.
# Usage: flask shell < seed_inventory.py  OR  python seed_inventory.py

from app import create_app, db

app = create_app()

with app.app_context():
    pass  # data will go here
