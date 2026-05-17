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
    with app.app_context():
        db.create_all()
        from app.models.user import User
        if not User.query.first():
            from app import bcrypt
            from app.models.site import Site
            from app.models.asset import AssetType
            admin = User(
                name='Admin',
                email='admin@inventory.app',
                password_hash=bcrypt.generate_password_hash('admin1234').decode(),
                role='admin',
            )
            db.session.add(admin)
            for name in ['Beit VaGan', 'Tel Aviv HQ', 'Haifa DC', 'Storage Warehouse']:
                db.session.add(Site(name=name))
            for name, cat in [
                ('SFP Module', 'Networking'), ('Switch', 'Networking'),
                ('Router', 'Networking'), ('Firewall', 'Security'),
                ('Server', 'Compute'), ('UPS', 'Power'),
            ]:
                db.session.add(AssetType(name=name, category=cat))
            db.session.commit()
            print('[Inventory] First run -- seeded admin user.')
            print('[Inventory] Login: admin@inventory.app / admin1234')

    app.run(debug=True, host='127.0.0.1', port=5000)
