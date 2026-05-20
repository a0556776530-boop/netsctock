import mongoengine as me
from datetime import datetime


class Contact(me.Document):
    meta = {'collection': 'contacts'}

    name       = me.StringField(max_length=150, required=True)
    email      = me.StringField(max_length=200)
    phone      = me.StringField(max_length=30)
    notes      = me.StringField()
    created_at = me.DateTimeField(default=datetime.utcnow)

    def __repr__(self):
        return f'<Contact {self.name}>'
