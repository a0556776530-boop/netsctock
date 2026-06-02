import logging
from datetime import datetime

_log = logging.getLogger(__name__)
_COLLECTION = 'login_events'


def _col():
    from mongoengine.connection import get_db
    return get_db('default')[_COLLECTION]


def get_ip(request):
    fwd = request.headers.get('X-Forwarded-For', '')
    return fwd.split(',')[0].strip() if fwd else (request.remote_addr or '0.0.0.0')


def record_login(*, user_name, user_role, ip, ua, success, user_id=None):
    try:
        _col().insert_one({
            'user_name':  user_name or '—',
            'user_role':  user_role or '—',
            'user_id':    user_id,
            'ip_address': ip or '0.0.0.0',
            'user_agent': (ua or '')[:500],
            'success':    bool(success),
            'timestamp':  datetime.utcnow(),
        })
    except Exception as e:
        _log.error('record_login failed: %s', e, exc_info=True)
