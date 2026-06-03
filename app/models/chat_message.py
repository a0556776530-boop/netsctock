import mongoengine as me
from datetime import datetime


def _private_room(uid1, uid2):
    """Consistent room key for two users regardless of order."""
    return 'pm_' + '_'.join(sorted([str(uid1), str(uid2)]))


class ChatMessage(me.Document):
    meta = {
        'collection': 'chat_messages',
        'ordering': ['-timestamp'],
        'indexes': [
            '-timestamp',
            'room',
            ('room', '-timestamp'),
            ('room', 'timestamp'),
        ],
        'strict': False,
    }

    # Core fields
    user_id     = me.StringField(required=True)
    user_name   = me.StringField(max_length=100, required=True)
    user_role   = me.StringField(max_length=20)
    text        = me.StringField(max_length=4000, default='')
    timestamp   = me.DateTimeField(default=datetime.utcnow)
    room        = me.StringField(max_length=120, default='group')
    receiver_id = me.StringField(max_length=50)   # only for PM rooms

    # Read tracking
    read        = me.BooleanField(default=False)  # legacy (PM only)
    readers     = me.ListField(me.StringField())  # list of user_ids who have read

    # Reply / quote
    reply_to_id   = me.StringField(max_length=50)
    reply_to_text = me.StringField(max_length=200)
    reply_to_user = me.StringField(max_length=100)

    # Reactions: {'👍': ['uid1', 'uid2'], '❤️': ['uid3']}
    reactions   = me.DictField()

    # Soft-delete
    deleted     = me.BooleanField(default=False)

    # File attachment (base64, max ~2 MB original)
    file_data   = me.StringField()     # base64-encoded content
    file_name   = me.StringField(max_length=200)
    file_type   = me.StringField(max_length=20)  # 'image'|'pdf'|'excel'|'file'
    file_size   = me.IntField()        # bytes

    def to_dict(self, viewer_id=None):
        txt = '[הודעה נמחקה]' if self.deleted else (self.text or '')
        return {
            'id':            str(self.id),
            'user_id':       self.user_id,
            'user_name':     self.user_name,
            'user_role':     self.user_role or '',
            'text':          txt,
            'deleted':       bool(self.deleted),
            'timestamp':     self.timestamp.strftime('%H:%M'),
            'date':          self.timestamp.strftime('%d/%m/%Y'),
            '_iso':          self.timestamp.isoformat(),
            'room':          self.room or 'group',
            'receiver_id':   self.receiver_id or '',
            'readers':       list(self.readers or []),
            'read':          bool(self.read),
            'reply_to_id':   self.reply_to_id or '',
            'reply_to_text': self.reply_to_text or '',
            'reply_to_user': self.reply_to_user or '',
            'reactions':     self.reactions or {},
            # Only include file data when needed
            'file_name':     self.file_name or '',
            'file_type':     self.file_type or '',
            'file_size':     self.file_size or 0,
            'has_file':      bool(self.file_data),
        }

    def to_dict_with_file(self, viewer_id=None):
        d = self.to_dict(viewer_id)
        d['file_data'] = self.file_data or ''
        return d
