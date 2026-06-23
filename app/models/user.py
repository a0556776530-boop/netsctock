from flask_login import UserMixin
from app import login_manager
import mongoengine as me
from datetime import datetime


class User(UserMixin, me.Document):
    meta = {'collection': 'users', 'strict': False, 'indexes': ['-last_seen', 'role']}

    name           = me.StringField(max_length=100, required=True)
    password_hash  = me.StringField(max_length=255, required=True)
    role           = me.StringField(max_length=20, default='viewer')
    created_at     = me.DateTimeField(default=datetime.utcnow)
    last_seen       = me.DateTimeField()
    last_login      = me.DateTimeField()
    pinned_rooms   = me.ListField(me.StringField())
    favorite_rooms = me.ListField(me.StringField())

    def get_id(self):
        return str(self.id)

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
        now = _dt.utcnow()
        cached = _user_cache.get(user_id)
        if cached and (now - cached[1]).total_seconds() < 10:
            return cached[0]
        user = User.objects(id=user_id).first()
        if user:
            _user_cache[user_id] = (user, now)
        return user
    except Exception:
        return None
