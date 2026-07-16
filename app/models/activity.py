import mongoengine as me
from datetime import datetime


class ActivityLog(me.Document):
    meta = {
        'collection': 'activity_log',
        'ordering': ['-created_at'],
        'index_background': True,
        'indexes': [
            '-created_at',
            {'fields': ['created_at'], 'expireAfterSeconds': 60 * 60 * 24 * 60},  # TTL 60 days
        ],
    }

    user_name   = me.StringField(max_length=150, required=True)
    user_role   = me.StringField(max_length=50)
    action_type = me.StringField(max_length=60, required=True)
    description = me.StringField(max_length=300, required=True)
    icon        = me.StringField(max_length=60, default='bi-circle')
    color       = me.StringField(max_length=30, default='secondary')
    created_at  = me.DateTimeField(default=datetime.utcnow)
