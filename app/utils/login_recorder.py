import logging
from datetime import datetime, timedelta

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
        col = _col()
        now = datetime.utcnow()

        # Dedup for successful logins: skip if same user logged in within 30 min
        if success and user_id:
            cutoff = now - timedelta(minutes=30)
            if col.find_one({'user_id': user_id, 'success': True,
                             'timestamp': {'$gte': cutoff}}, {'_id': 1}):
                return

        # Dedup for failed logins: skip if same IP already has a failure in last 5 min
        # (prevents log spam from double-clicks or rapid retries, but still captures all IPs)
        if not success and ip and ip not in ('0.0.0.0', '127.0.0.1', '::1'):
            cutoff = now - timedelta(minutes=5)
            if col.find_one({'ip_address': ip, 'success': False,
                             'timestamp': {'$gte': cutoff}}, {'_id': 1}):
                return

        col.insert_one({
            'user_name':  user_name or '—',
            'user_role':  user_role or '—',
            'user_id':    user_id,
            'ip_address': ip or '0.0.0.0',
            'user_agent': (ua or '')[:500],
            'success':    bool(success),
            'timestamp':  now,
        })
    except Exception as e:
        _log.error('record_login failed: %s', e, exc_info=True)
