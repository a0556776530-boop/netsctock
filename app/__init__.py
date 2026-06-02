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

    from flask_login import user_loaded_from_cookie
    from flask import request as _flask_req

    @user_loaded_from_cookie.connect_via(app)
    def _on_cookie_login(sender, user):
        try:
            from .utils.login_recorder import record_login, get_ip
            record_login(
                user_name=user.name,
                user_role=user.role,
                user_id=str(user.id),
                ip=get_ip(_flask_req),
                ua=_flask_req.headers.get('User-Agent', ''),
                success=True,
            )
        except Exception:
            pass

    from .routes.auth import auth_bp
    from .routes.main import main_bp
    from .routes.assets import assets_bp
    from .routes.tasks import tasks_bp
    from .routes.admin import admin_bp
    from .routes.estimates import estimates_bp
    from .routes.purchases import purchases_bp
    from .routes.pools import pools_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(assets_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(estimates_bp)
    app.register_blueprint(purchases_bp)
    app.register_blueprint(pools_bp)

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

        # Update last_seen on every authenticated request
        if current_user.is_authenticated:
            from .models.user import User
            User.objects(id=current_user.id).update_one(set__last_seen=datetime.utcnow())


    from zoneinfo import ZoneInfo
    from datetime import timezone as _tz
    _IL = ZoneInfo('Asia/Jerusalem')

    @app.template_filter('localtime')
    def localtime_filter(dt):
        if dt is None:
            return dt
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_tz.utc)
        return dt.astimezone(_IL)

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
