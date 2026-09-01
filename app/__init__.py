import traceback as _tb
from flask import Flask
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import mongoengine as me

import click
from .config import Config, MONGO_URI

login_manager = LoginManager()
bcrypt        = Bcrypt()
csrf          = CSRFProtect()
limiter       = Limiter(key_func=get_remote_address, default_limits=[])

from .utils.cache import cache

# Expose db as the mongoengine module so models can do `from app import db`
# and call db.Document, db.StringField, etc.
db = me


def _avatar_color(name):
    _pal = ['#3b82f6','#8b5cf6','#10b981','#f59e0b','#ef4444','#06b6d4','#ec4899','#f97316']
    if not name:
        return _pal[0]
    return _pal[hash(name) % len(_pal)]


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Connect MongoEngine to Atlas
    me.connect(host=MONGO_URI, alias='default',
               serverSelectionTimeoutMS=15000,
               socketTimeoutMS=20000,
               connectTimeoutMS=10000,
               maxPoolSize=100,
               minPoolSize=5,
               maxIdleTimeMS=45000,
               retryWrites=True)

    login_manager.init_app(app)
    bcrypt.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    cache.init_app(app, config={'CACHE_TYPE': 'SimpleCache', 'CACHE_DEFAULT_TIMEOUT': 60})

    # Jinja2 globals — set once at startup, zero per-request cost
    app.jinja_env.globals['avatar_color'] = _avatar_color

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
        session.permanent = True  # enforce PERMANENT_SESSION_LIFETIME idle timeout
        lang = session.get('lang', 'en')
        if lang not in TRANSLATIONS:
            lang = 'en'
        g.lang = lang
        g.t = TRANSLATIONS[lang]
        g.dir_html = 'rtl' if lang == 'he' else 'ltr'



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
            'unread_total': 0,
        }

    from .seed import register_commands
    register_commands(app)

    @app.after_request
    def set_security_headers(response):
        response.headers.setdefault('X-Frame-Options', 'DENY')
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        response.headers.setdefault('Permissions-Policy', 'geolocation=(), microphone=(), camera=(self)')
        response.headers.setdefault('Content-Security-Policy',
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "font-src 'self' data:; "
            "img-src 'self' data: blob:; "
            "connect-src 'self' ws: wss:; "
            "frame-ancestors 'none';"
        )
        return response

    @app.errorhandler(429)
    def handle_429(e):
        from flask import render_template_string
        return render_template_string(
            '<html><body style="font-family:sans-serif;padding:40px;direction:ltr;text-align:center">'
            '<h2 style="color:#dc2626">Too Many Attempts</h2>'
            '<p>Too many login attempts. Please wait a minute and try again.</p>'
            '<a href="/auth/login">Back to Login</a></body></html>'
        ), 429

    @app.errorhandler(500)
    def handle_500(e):
        tb = _tb.format_exc()
        app.logger.error('500 error:\n' + tb)
        from flask import render_template_string
        detail = tb if app.debug else 'An internal server error occurred. Please try again or contact your administrator.'
        return render_template_string(
            '<html><body style="font-family:monospace;padding:20px;direction:ltr">'
            '<h2 style="color:#dc2626">Server Error</h2>'
            '<pre style="background:#fee2e2;padding:12px;border-radius:6px;white-space:pre-wrap;font-size:.85rem">{{ detail }}</pre>'
            '<a href="/">Back to Home</a></body></html>',
            detail=detail
        ), 500

    return app
