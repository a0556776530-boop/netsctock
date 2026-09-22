import mongoengine as me
from datetime import datetime


class ActivityLog(me.Document):
    """A lightweight, general activity feed (task/asset/allocation/estimate
    creation) shown on the dashboard. Entries older than RETENTION_DAYS are
    purged automatically whenever a new one is logged — see log_activity()
    in app/utils/activity.py."""

    meta = {
        'collection': 'activity_log',
        'indexes': ['-created_at'],
        'ordering': ['-created_at'],
    }

    RETENTION_DAYS = 180  # ~6 months

    ACTION_TYPES = ['task_created', 'asset_created', 'allocation_created', 'estimate_created']
    ACTION_LABELS = {
        'task_created':       'משימה חדשה',
        'asset_created':      'פריט חדש',
        'allocation_created': 'הקצאה חדשה',
        'estimate_created':   'אומדן חדש',
    }
    ACTION_ICONS = {
        'task_created':       'bi-list-task',
        'asset_created':      'bi-cpu',
        'allocation_created': 'bi-clipboard2-data',
        'estimate_created':   'bi-calculator',
    }
    ACTION_COLORS = {
        'task_created':       '#f59e0b',
        'asset_created':      '#0d6efd',
        'allocation_created': '#198754',
        'estimate_created':   '#8b5cf6',
    }

    action       = me.StringField(required=True, choices=ACTION_TYPES)
    description  = me.StringField(required=True, max_length=255)
    performed_by = me.StringField(max_length=100)
    created_at   = me.DateTimeField(default=datetime.utcnow)

    def __repr__(self):
        return f'<ActivityLog {self.action}: {self.description}>'

    @property
    def action_label(self):
        return self.ACTION_LABELS.get(self.action, self.action)

    @property
    def action_icon(self):
        return self.ACTION_ICONS.get(self.action, 'bi-circle')

    @property
    def action_color(self):
        return self.ACTION_COLORS.get(self.action, 'secondary')
