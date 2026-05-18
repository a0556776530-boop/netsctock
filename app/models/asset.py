from app import db
from datetime import datetime


class AssetType(db.Model):
    __tablename__ = 'asset_types'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(100))

    assets = db.relationship('Asset', backref='asset_type', lazy='dynamic')

    def __repr__(self):
        return f'<AssetType {self.name}>'


class Asset(db.Model):
    __tablename__ = 'assets'

    STATUSES = ['in_use', 'dismantled', 'in_storage', 'assigned', 'faulty', 'retired']
    STATUS_LABELS = {
        'in_use': 'בשימוש',
        'dismantled': 'פורק',
        'in_storage': 'באחסון',
        'assigned': 'מוקצה',
        'faulty': 'פגום',
        'retired': 'הוצא משירות',
    }
    STATUS_COLORS = {
        'in_use': 'success',
        'dismantled': 'warning',
        'in_storage': 'info',
        'assigned': 'primary',
        'faulty': 'danger',
        'retired': 'secondary',
    }

    id = db.Column(db.Integer, primary_key=True)
    component_id = db.Column(db.String(50), nullable=True)
    serial_number = db.Column(db.String(100), unique=True, nullable=False)
    barcode = db.Column(db.String(100), unique=True, nullable=True)
    asset_type_id = db.Column(db.Integer, db.ForeignKey('asset_types.id'), nullable=False)
    model = db.Column(db.String(150))
    manufacturer = db.Column(db.String(150))
    status = db.Column(
        db.Enum(*STATUSES, name='asset_status'),
        nullable=False,
        default='in_storage'
    )
    current_site_id = db.Column(db.Integer, db.ForeignKey('sites.id'), nullable=True)
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    notes = db.Column(db.Text)
    price          = db.Column(db.Numeric(12, 2), nullable=True)
    price_nis      = db.Column(db.Numeric(12, 2), nullable=True)
    price_usd      = db.Column(db.Numeric(12, 2), nullable=True)
    conversion_fee = db.Column(db.Numeric(5, 2), nullable=True)
    quantity       = db.Column(db.Integer, nullable=True)
    min_threshold  = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    events = db.relationship('AssetEvent', backref='asset', lazy='dynamic',
                             order_by='AssetEvent.event_date.desc()')
    tasks = db.relationship('Task', backref='asset', lazy='dynamic')

    def __repr__(self):
        return f'<Asset {self.serial_number}>'

    @property
    def status_label(self):
        return self.STATUS_LABELS.get(self.status, self.status)

    @property
    def status_color(self):
        return self.STATUS_COLORS.get(self.status, 'secondary')



class AssetEvent(db.Model):
    __tablename__ = 'asset_events'

    EVENT_TYPES = ['dismantled', 'moved', 'assigned', 'returned', 'repaired',
                   'created', 'retired', 'status_change']
    EVENT_LABELS = {
        'dismantled': 'פורק',
        'moved': 'הועבר',
        'assigned': 'הוקצה',
        'returned': 'הוחזר',
        'repaired': 'תוקן',
        'created': 'נוצר',
        'retired': 'הוצא משירות',
        'status_change': 'סטטוס שונה',
    }
    EVENT_ICONS = {
        'dismantled': 'bi-tools',
        'moved': 'bi-arrow-left-right',
        'assigned': 'bi-person-check',
        'returned': 'bi-arrow-return-left',
        'repaired': 'bi-wrench',
        'created': 'bi-plus-circle',
        'retired': 'bi-archive',
        'status_change': 'bi-arrow-repeat',
    }

    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('assets.id'), nullable=False)
    event_type = db.Column(
        db.Enum(*EVENT_TYPES, name='event_type'),
        nullable=False
    )
    from_site_id = db.Column(db.Integer, db.ForeignKey('sites.id'), nullable=True)
    to_site_id = db.Column(db.Integer, db.ForeignKey('sites.id'), nullable=True)
    performed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    notes = db.Column(db.Text)
    event_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<AssetEvent {self.event_type} on asset {self.asset_id}>'

    @property
    def event_label(self):
        return self.EVENT_LABELS.get(self.event_type, self.event_type)

    @property
    def event_icon(self):
        return self.EVENT_ICONS.get(self.event_type, 'bi-circle')
