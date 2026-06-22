import mongoengine as me
from datetime import datetime


class ChatLastRead(me.Document):
    """Tracks when each user last read each room (groups, channels, everyone)."""
    meta = {
        'collection': 'chat_last_read',
        'indexes': [
            {'fields': ['user_id', 'room'], 'unique': True},
        ],
        'strict': False,
    }

    user_id      = me.StringField(required=True)
    room         = me.StringField(max_length=120, required=True)
    last_read_at = me.DateTimeField(default=datetime.utcnow)
