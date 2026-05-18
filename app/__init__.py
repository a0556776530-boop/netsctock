from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_mail import Mail
from flask_wtf.csrf import CSRFProtect

import click
from .config import Config

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
bcrypt = Bcrypt()
mail = Mail()
csrf = CSRFProtect()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    mail.init_app(app)
    csrf.init_app(app)

    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'warning'

    # Import models so Flask-Migrate detects them
    from .models import user, asset, site, task, settings, estimate  # noqa: F401

    from .routes.auth import auth_bp
    from .routes.main import main_bp
    from .routes.assets import assets_bp
    from .routes.sites import sites_bp
    from .routes.scan import scan_bp
    from .routes.tasks import tasks_bp
    from .routes.admin import admin_bp
    from .routes.estimates import estimates_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(assets_bp)
    app.register_blueprint(sites_bp)
    app.register_blueprint(scan_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(estimates_bp)

    from datetime import datetime
    from .utils.translations import TRANSLATIONS

    @app.before_request
    def set_locale():
        from flask import g, session
        lang = session.get('lang', 'en')
        if lang not in TRANSLATIONS:
            lang = 'en'
        g.lang = lang
        g.t = TRANSLATIONS[lang]
        g.dir_html = 'rtl' if lang == 'he' else 'ltr'

    @app.context_processor
    def inject_globals():
        from flask import g
        from .utils.exchange import get_usd_to_nis
        return {
            'now': datetime.utcnow(),
            'usd_nis_rate': get_usd_to_nis(),
            'lang': getattr(g, 'lang', 'en'),
            'dir_html': getattr(g, 'dir_html', 'ltr'),
            't': getattr(g, 't', TRANSLATIONS['en']),
        }

    # CLI: flask seed-db / flask send-reminders
    from .seed import register_commands
    register_commands(app)
    _register_email_commands(app)

    return app


def _register_email_commands(app):
    @app.cli.command('send-reminders')
    def send_reminders():
        """Send due date reminder emails to all users with overdue/upcoming items."""
        from .utils.email import send_due_reminders
        count = send_due_reminders()
        click.echo(f'Sent {count} reminder email(s).')
