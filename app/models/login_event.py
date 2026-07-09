import mongoengine as me
from datetime import datetime


class LoginEvent(me.Document):
    meta = {
        'collection': 'login_events',
        'ordering': ['-timestamp'],
        'strict': False,
        'index_background': True,
        'indexes': [
            'user_name',
            'ip_address',
            # Compound indexes for dedup queries in login_recorder.py
            ('user', 'ip_address', 'success', '-timestamp'),
            ('ip_address', 'user_agent', 'success', '-timestamp'),
            # TTL — auto-delete records older than 90 days
            {'fields': ['timestamp'], 'expireAfterSeconds': 7776000},
        ],
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
