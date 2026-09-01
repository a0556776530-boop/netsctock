from flask_login import UserMixin
from app import login_manager
import mongoengine as me
from datetime import datetime


class User(UserMixin, me.Document):
    meta = {'collection': 'users', 'strict': False,
            'indexes': ['-last_seen', 'role', {'fields': ['username'], 'unique': True, 'sparse': True}]}

    name           = me.StringField(max_length=100, required=True)
    username       = me.StringField(max_length=50, sparse=True)  # unique login identifier; sparse = NULLs allowed
    password_hash  = me.StringField(max_length=255, required=True)
    role           = me.StringField(max_length=20, default='viewer')
    created_at     = me.DateTimeField(default=datetime.utcnow)
    last_seen       = me.DateTimeField()
    last_login      = me.DateTimeField()
    profile_photo   = me.StringField()  # base64 data URI e.g. "data:image/jpeg;base64,..."
    session_version = me.IntField(default=0)

    def get_id(self):
        return f"{self.id}:{self.session_version or 0}"

    def __repr__(self):
        return f'<User {self.name}>'

    @property
    def is_super_admin(self):
        return self.role == 'super_admin'

    @property
    def is_admin(self):
        return self.role in ('admin', 'super_admin')

    @property
    def can_edit(self):
        return self.role in ('admin', 'super_admin')

    @property
    def is_warehouse(self):
        return self.role == 'warehouse'


_user_cache: dict = {}  # {user_id: (User, timestamp)}


@login_manager.user_loader
def load_user(user_id):
    try:
        from datetime import datetime as _dt
        # user_id format: "<mongo_id>:<session_version>"
        parts = user_id.split(':', 1)
        oid   = parts[0]
        sv    = int(parts[1]) if len(parts) > 1 else 0

        now = _dt.utcnow()
        cached = _user_cache.get(oid)
        if cached and (now - cached[1]).total_seconds() < 10:
            user = cached[0]
        else:
            user = User.objects(id=oid).first()
            if user:
                _user_cache[oid] = (user, now)
        if not user:
            return None
        # Reject session if password was changed since login
        if (user.session_version or 0) != sv:
            return None
        return user
    except Exception:
        return None
