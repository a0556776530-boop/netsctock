import mongoengine as me
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_IL = ZoneInfo('Asia/Jerusalem')


def _private_room(uid1, uid2):
    """Consistent room key for two users regardless of order."""
    return 'pm_' + '_'.join(sorted([str(uid1), str(uid2)]))


class ChatMessage(me.Document):
    meta = {
        'collection': 'chat_messages',
        'ordering': ['-timestamp'],
        'index_background': True,
        'indexes': [
            ('room', '-timestamp'),            # main query: messages in a room, newest first
            ('receiver_id', 'read', 'room'),   # unread-count aggregation + per-room read updates
            'user_id',                         # user message history
            'deleted',                         # search/list filters
            {'fields': ['file_id'], 'sparse': True},  # file cleanup queries
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

    # Soft-delete + edit
    deleted     = me.BooleanField(default=False)
    edited      = me.BooleanField(default=False)

    # Forward
    forwarded     = me.BooleanField(default=False)
    forward_from  = me.StringField(max_length=100)

    # File attachment — data stored in ChatFile collection (keeps messages lightweight)
    file_id     = me.StringField(max_length=50)   # ChatFile._id
    file_name   = me.StringField(max_length=200)
    file_type   = me.StringField(max_length=20)   # 'image'|'pdf'|'excel'|'file'
    file_size   = me.IntField()                   # bytes

    def to_dict(self, viewer_id=None, receiver_online=False):
        txt = '[הודעה נמחקה]' if self.deleted else (self.text or '')
        return {
            'id':            str(self.id),
            'user_id':       self.user_id,
            'user_name':     self.user_name,
            'user_role':     self.user_role or '',
            'text':          txt,
            'deleted':       bool(self.deleted),
            'timestamp':     self.timestamp.replace(tzinfo=timezone.utc).astimezone(_IL).strftime('%H:%M'),
            'date':          self.timestamp.replace(tzinfo=timezone.utc).astimezone(_IL).strftime('%d/%m/%Y'),
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
            'file_id':       self.file_id or '',
            'file_name':     self.file_name or '',
            'file_type':     self.file_type or '',
            'file_size':     self.file_size or 0,
            'has_file':      bool(self.file_id),
            'edited':        bool(self.edited),
            'forwarded':        bool(self.forwarded),
            'forward_from':     self.forward_from or '',
            'receiver_online':  bool(receiver_online),
        }

