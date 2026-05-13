from app import db
from datetime import datetime, date


class Task(db.Model):
    __tablename__ = 'tasks'

    STATUSES = ['pending', 'in_progress', 'done']
    STATUS_LABELS = {
        'pending': 'ממתין',
        'in_progress': 'בביצוע',
        'done': 'הושלם',
    }
    STATUS_COLORS = {
        'pending': 'warning',
        'in_progress': 'primary',
        'done': 'success',
    }

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    asset_id = db.Column(db.Integer, db.ForeignKey('assets.id'), nullable=True)
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    due_date = db.Column(db.Date, nullable=True)
    status = db.Column(
        db.Enum(*STATUSES, name='task_status'),
        nullable=False,
        default='pending'
    )
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Task {self.title}>'

    @property
    def status_label(self):
        return self.STATUS_LABELS.get(self.status, self.status)

    @property
    def status_color(self):
        return self.STATUS_COLORS.get(self.status, 'secondary')

    @property
    def is_overdue(self):
        return self.due_date and self.due_date < date.today() and self.status != 'done'
