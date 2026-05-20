from flask_login import UserMixin
from app import login_manager
import mongoengine as me
from datetime import datetime


class User(UserMixin, me.Document):
    meta = {'collection': 'users'}

    name          = me.StringField(max_length=100, required=True)
    email         = me.StringField(max_length=150, required=True, unique=True)
    password_hash = me.StringField(max_length=255, required=True)
    role          = me.StringField(max_length=20, default='technician')
    created_at    = me.DateTimeField(default=datetime.utcnow)

    def get_id(self):
        return str(self.id)

    def __repr__(self):
        return f'<User {self.email}>'

    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def can_edit(self):
        return self.role in ('admin', 'technician')


@login_manager.user_loader
def load_user(user_id):
    return User.objects(id=user_id).first()
