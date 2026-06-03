import mongoengine as me
from datetime import datetime


def _private_room(uid1, uid2):
    """Consistent room key for two users regardless of order."""
    return 'pm_' + '_'.join(sorted([str(uid1), str(uid2)]))


class ChatMessage(me.Document):
    meta = {
        'collection': 'chat_messages',
        'ordering': ['-timestamp'],
        'indexes': ['-timestamp', 'room', ('room', '-timestamp')],
        'strict': False,
    }

    user_id     = me.StringField(required=True)
    user_name   = me.StringField(max_length=100, required=True)
    user_role   = me.StringField(max_length=20)
    text        = me.StringField(max_length=2000, required=True)
    timestamp   = me.DateTimeField(default=datetime.utcnow)
    # 'group' = group chat, 'pm_<uid1>_<uid2>' = private
    room        = me.StringField(max_length=120, default='group')
    # For private messages: ID of the other participant
    receiver_id = me.StringField(max_length=50)
    read        = me.BooleanField(default=False)

    def to_dict(self):
        return {
            'id':          str(self.id),
            'user_id':     self.user_id,
            'user_name':   self.user_name,
            'user_role':   self.user_role or '',
            'text':        self.text,
            'timestamp':   self.timestamp.strftime('%H:%M'),
            'date':        self.timestamp.strftime('%d/%m/%Y'),
            'room':        self.room or 'group',
            'receiver_id': self.receiver_id or '',
            '_iso':        self.timestamp.isoformat(),
        }
