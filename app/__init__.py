import traceback as _tb
from flask import Flask
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_wtf.csrf import CSRFProtect
from flask_socketio import SocketIO
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import mongoengine as me

import click
from .config import Config, MONGO_URI

login_manager = LoginManager()
bcrypt        = Bcrypt()
csrf          = CSRFProtect()
socketio      = SocketIO()
limiter       = Limiter(key_func=get_remote_address, default_limits=[])

from .utils.cache import cache

# Expose db as the mongoengine module so models can do `from app import db`
# and call db.Document, db.StringField, etc.
db = me


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

    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'warning'

    from flask_login import user_loaded_from_cookie
    from flask import request as _flask_req

    _cookie_login_seen: dict = {}  # uid -> last recorded timestamp

    @user_loaded_from_cookie.connect_via(app)
    def _on_cookie_login(sender, user):
        try:
            from datetime import datetime as _dt
            uid = str(user.id)
            now = _dt.utcnow()
            last = _cookie_login_seen.get(uid)
            if last and (now - last).total_seconds() < 300:
                return  # skip DB query — recorded within last 5 min
            _cookie_login_seen[uid] = now
            from .utils.login_recorder import record_login, get_ip
            record_login(
                user_name=user.name,
                user_role=user.role,
                user_id=uid,
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
    from .routes.chat import chat_bp
    from .routes import chat_socket as _chat_socket  # register socket handlers  # noqa: F401

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(assets_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(estimates_bp)
    app.register_blueprint(purchases_bp)
    app.register_blueprint(pools_bp)
    app.register_blueprint(chat_bp)

    import os as _os
    _origin_env = _os.environ.get('ALLOWED_ORIGIN', '').strip()
    _cors = [o.strip() for o in _origin_env.split(',') if o.strip()] if _origin_env else '*'
    socketio.init_app(
        app,
        cors_allowed_origins=_cors,
        async_mode='threading',
        logger=False,
        engineio_logger=False,
        ping_timeout=25,
        ping_interval=15,
        allow_upgrades=True,
        transports=['websocket', 'polling'],
    )

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

        # Update last_seen — throttled to once per 30s to avoid write on every AJAX call
        if current_user.is_authenticated:
            now = datetime.utcnow()
            ls = current_user.last_seen
            if ls is None or (now - ls).total_seconds() > 30:
                from .models.user import User
                User.objects(id=current_user.id).update_one(set__last_seen=now)
                current_user.last_seen = now


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

    # Ensure login_events indexes (incl. TTL) exist on the live collection
    try:
        from .models.login_event import LoginEvent
        LoginEvent.ensure_indexes()
    except Exception:
        pass

    try:
        from .models.activity import ActivityLog
        ActivityLog.ensure_indexes()
    except Exception:
        pass

    @app.after_request
    def set_security_headers(response):
        response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-XSS-Protection', '1; mode=block')
        response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
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
