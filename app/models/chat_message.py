import mongoengine as me
from datetime import datetime


class ChatMessage(me.Document):
    meta = {
        'collection': 'chat_messages',
        'ordering': ['-timestamp'],
        'indexes': ['-timestamp'],
        'strict': False,
    }

    user_id   = me.StringField(required=True)
    user_name = me.StringField(max_length=100, required=True)
    user_role = me.StringField(max_length=20)
    text      = me.StringField(max_length=2000, required=True)
    timestamp = me.DateTimeField(default=datetime.utcnow)

    def to_dict(self):
        return {
            'id':        str(self.id),
            'user_id':   self.user_id,
            'user_name': self.user_name,
            'user_role': self.user_role or '',
            'text':      self.text,
            'timestamp': self.timestamp.strftime('%H:%M'),
            'date':      self.timestamp.strftime('%d/%m/%Y'),
        }
