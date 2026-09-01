import os
import click
from app import bcrypt
from app.models.user import User
from app.models.asset import AssetType


def register_commands(app):
    @app.cli.command('seed-db')
    @click.option('--password', prompt=True, hide_input=True,
                  help='Password for the initial super_admin user (min 8 chars).')
    def seed_db(password):
        """Create initial super_admin user and seed reference data."""
        if len(password) < 8:
            click.echo('Error: password must be at least 8 characters.', err=True)
            raise SystemExit(1)
        if not User.objects(name='Admin').first():
            User(
                name='Admin',
                password_hash=bcrypt.generate_password_hash(password).decode('utf-8'),
                role='super_admin',
            ).save()
            click.echo('  Created super_admin user: Admin')
        else:
            click.echo('  Admin user already exists — skipped.')

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
