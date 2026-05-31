import traceback as _tb
from flask import Flask
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_wtf.csrf import CSRFProtect
import mongoengine as me

import click
from .config import Config, MONGO_URI

login_manager = LoginManager()
bcrypt = Bcrypt()
csrf = CSRFProtect()

# Expose db as the mongoengine module so models can do `from app import db`
# and call db.Document, db.StringField, etc.
db = me


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Connect MongoEngine to Atlas
    me.connect(host=MONGO_URI, alias='default')

    login_manager.init_app(app)
    bcrypt.init_app(app)
    csrf.init_app(app)

    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'warning'

    from .routes.auth import auth_bp
    from .routes.main import main_bp
    from .routes.assets import assets_bp
    from .routes.tasks import tasks_bp
    from .routes.admin import admin_bp
    from .routes.estimates import estimates_bp
    from .routes.purchases import purchases_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(assets_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(estimates_bp)
    app.register_blueprint(purchases_bp)

    from datetime import datetime
    from .utils.translations import TRANSLATIONS

    @app.before_request
    def set_locale():
        from flask import g, session
        from flask_login import current_user
        lang = session.get('lang', 'en')
        if lang not in TRANSLATIONS:
            lang = 'en'
        g.lang = lang
        g.t = TRANSLATIONS[lang]
        g.dir_html = 'rtl' if lang == 'he' else 'ltr'

        # Update last_seen on every request for authenticated users
        if current_user.is_authenticated:
            from .models.user import User
            User.objects(id=current_user.id).update_one(set__last_seen=datetime.utcnow())

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

    from .seed import register_commands
    register_commands(app)

    @app.errorhandler(500)
    def handle_500(e):
        tb = _tb.format_exc()
        app.logger.error('500 error:\n' + tb)
        from flask import render_template_string
        return render_template_string(
            '<html><body style="font-family:monospace;padding:20px;direction:ltr">'
            '<h2 style="color:#dc2626">Server Error</h2>'
            '<pre style="background:#fee2e2;padding:12px;border-radius:6px;white-space:pre-wrap;font-size:.85rem">{{ tb }}</pre>'
            '<a href="/">Back to Home</a></body></html>',
            tb=tb
        ), 500

    return app
