from flask_login import UserMixin
from app import db, login_manager
from datetime import datetime


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum('admin', 'technician', 'viewer', name='user_role'),
                     nullable=False, default='technician')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    assigned_assets = db.relationship('Asset', foreign_keys='Asset.assigned_to_id',
                                      backref='assignee', lazy='dynamic')
    events = db.relationship('AssetEvent', backref='performed_by_user', lazy='dynamic')
    tasks = db.relationship('Task', backref='assignee', lazy='dynamic')

    def __repr__(self):
        return f'<User {self.email}>'

    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def can_edit(self):
        return self.role in ('admin', 'technician')


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
