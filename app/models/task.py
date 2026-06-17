import mongoengine as me
from datetime import datetime


class Task(me.Document):
    meta = {
        'collection': 'tasks',
        'strict': False,
        'index_background': True,
        'indexes': [
            'status',
            '-created_at',
            ('assignee_name', 'status'),  # admin users page N+1: tasks per user by status
        ],
    }

    STATUSES = ['pending', 'in_progress', 'done']  # 'pending' kept for legacy docs
    STATUS_LABELS = {'pending': 'In Progress', 'in_progress': 'In Progress', 'done': 'Done'}
    STATUS_COLORS = {'pending': 'primary', 'in_progress': 'primary', 'done': 'success'}

    title         = me.StringField(max_length=255, required=True)
    assignee_name = me.StringField(max_length=200)
    status        = me.StringField(default='in_progress', choices=STATUSES)
    notes         = me.StringField()
    created_at    = me.DateTimeField(default=datetime.utcnow)

    def __repr__(self):
        return f'<Task {self.title}>'

    @property
    def status_label(self):
        return self.STATUS_LABELS.get(self.status, self.status)

    @property
    def status_color(self):
        return self.STATUS_COLORS.get(self.status, 'secondary')
