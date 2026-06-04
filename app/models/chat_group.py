import mongoengine as me
from datetime import datetime


class ChatGroup(me.Document):
    meta = {
        'collection': 'chat_groups',
        'ordering': ['name'],
        'strict': False,
        'index_background': True,
        'indexes': ['member_ids', 'name'],  # member_ids: sidebar query; name: ordering
    }

    name        = me.StringField(max_length=100, required=True)
    description = me.StringField(max_length=300)
    creator_id  = me.StringField(required=True)
    member_ids  = me.ListField(me.StringField())
    created_at  = me.DateTimeField(default=datetime.utcnow)

    @property
    def room_key(self):
        return f'grp_{self.id}'

    def is_member(self, user_id):
        return str(user_id) in self.member_ids

    def __repr__(self):
        return f'<ChatGroup {self.name}>'
