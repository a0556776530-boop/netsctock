import mongoengine as me


class Site(me.Document):
    meta = {'collection': 'sites'}

    name    = me.StringField(max_length=150, required=True)
    address = me.StringField()
    notes   = me.StringField()

    def __repr__(self):
        return f'<Site {self.name}>'
