import mongoengine as me
from datetime import datetime


class ChatFile(me.Document):
    """Stores file attachments separately so ChatMessage stays lightweight."""
    meta = {
        'collection': 'chat_files',
        'indexes': ['-uploaded_at'],
        'strict': False,
    }

    data        = me.StringField(required=True)   # base64 data URI
    name        = me.StringField(max_length=200)
    file_type   = me.StringField(max_length=20)   # image|pdf|excel|file
    size        = me.IntField()                   # original bytes
    uploaded_at = me.DateTimeField(default=datetime.utcnow)
