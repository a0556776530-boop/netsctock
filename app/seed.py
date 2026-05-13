import click
from flask import current_app
from app import db, bcrypt
from app.models.user import User
from app.models.site import Site
from app.models.asset import AssetType


def register_commands(app):
    @app.cli.command('seed-db')
    def seed_db():
        """Create initial admin user and seed reference data."""
        db.create_all()

        if not User.query.filter_by(email='admin@netstock.app').first():
            admin = User(
                name='Admin',
                email='admin@netstock.app',
                password_hash=bcrypt.generate_password_hash('admin1234').decode('utf-8'),
                role='admin',
            )
            db.session.add(admin)
            click.echo('  Created admin user: admin@netstock.app / admin1234')

        sites = ['Beit VaGan', 'Tel Aviv HQ', 'Haifa DC', 'Storage Warehouse']
        for name in sites:
            if not Site.query.filter_by(name=name).first():
                db.session.add(Site(name=name))
                click.echo(f'  Created site: {name}')

        asset_types = [
            ('SFP Module', 'Networking'),
            ('Switch', 'Networking'),
            ('Router', 'Networking'),
            ('Patch Panel', 'Networking'),
            ('Firewall', 'Security'),
            ('Server', 'Compute'),
            ('UPS', 'Power'),
            ('Cable', 'Cabling'),
        ]
        for name, category in asset_types:
            if not AssetType.query.filter_by(name=name).first():
                db.session.add(AssetType(name=name, category=category))
                click.echo(f'  Created asset type: {name}')

        db.session.commit()
        click.echo('Database seeded successfully.')
