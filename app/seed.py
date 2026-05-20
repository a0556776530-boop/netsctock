import click
from app import bcrypt
from app.models.user import User
from app.models.site import Site
from app.models.asset import AssetType


def register_commands(app):
    @app.cli.command('seed-db')
    def seed_db():
        """Create initial admin user and seed reference data."""
        if not User.objects(email='admin@inventory.app').first():
            User(
                name='Admin',
                email='admin@inventory.app',
                password_hash=bcrypt.generate_password_hash('admin1234').decode('utf-8'),
                role='admin',
            ).save()
            click.echo('  Created admin user: admin@inventory.app / admin1234')

        for name in ['Beit VaGan', 'Tel Aviv HQ', 'Haifa DC', 'Storage Warehouse']:
            if not Site.objects(name=name).first():
                Site(name=name).save()
                click.echo(f'  Created site: {name}')

        for name, category in [
            ('SFP Module', 'Networking'), ('Switch', 'Networking'),
            ('Router', 'Networking'), ('Patch Panel', 'Networking'),
            ('Firewall', 'Security'), ('Server', 'Compute'),
            ('UPS', 'Power'), ('Cable', 'Cabling'),
        ]:
            if not AssetType.objects(name=name).first():
                AssetType(name=name, category=category).save()
                click.echo(f'  Created asset type: {name}')

        click.echo('Database seeded successfully.')
