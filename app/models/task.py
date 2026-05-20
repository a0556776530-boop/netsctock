import mongoengine as me
from datetime import datetime


class Task(me.Document):
    meta = {'collection': 'tasks'}

    STATUSES = ['pending', 'in_progress', 'done']
    STATUS_LABELS = {'pending': 'ממתין', 'in_progress': 'בביצוע', 'done': 'הושלם'}
    STATUS_COLORS = {'pending': 'warning', 'in_progress': 'primary', 'done': 'success'}

    title      = me.StringField(max_length=255, required=True)
    asset      = me.ReferenceField('Asset')
    assignee   = me.ReferenceField('User')
    status     = me.StringField(default='pending')
    notes      = me.StringField()
    created_at = me.DateTimeField(default=datetime.utcnow)

    def __repr__(self):
        return f'<Task {self.title}>'

    @property
    def status_label(self):
        return self.STATUS_LABELS.get(self.status, self.status)

    @property
    def status_color(self):
        return self.STATUS_COLORS.get(self.status, 'secondary')
