import mongoengine as me
from datetime import datetime


class LoginEvent(me.Document):
    meta = {
        'collection': 'login_events',
        'ordering': ['-timestamp'],
        'indexes': ['-timestamp', 'user_name', 'ip_address'],
        'strict': False,
    }

    user        = me.ReferenceField('User', db_field='user_id', required=False)
    user_name   = me.StringField(max_length=100)
    user_role   = me.StringField(max_length=20)
    timestamp   = me.DateTimeField(default=datetime.utcnow)
    ip_address  = me.StringField(max_length=45)
    user_agent  = me.StringField(max_length=500)
    success     = me.BooleanField(default=True)

    def __repr__(self):
        return f'<LoginEvent {self.user_name} {self.timestamp}>'
