import mongoengine as me
from datetime import datetime


class ChatTyping(me.Document):
    """Tracks who is currently typing in a room. Documents expire after 5s."""
    meta = {
        'collection': 'chat_typing',
        'indexes': [
            {'fields': ['ts'], 'expireAfterSeconds': 3},
            ('room', 'user_id'),
        ],
        'strict': False,
    }

    user_id   = me.StringField(required=True)
    user_name = me.StringField(max_length=100, required=True)
    room      = me.StringField(max_length=120, required=True)
    ts        = me.DateTimeField(default=datetime.utcnow)
