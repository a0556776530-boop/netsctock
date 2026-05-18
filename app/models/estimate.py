from datetime import datetime
from app import db


class Estimate(db.Model):
    __tablename__ = 'estimates'

    id                = db.Column(db.Integer, primary_key=True)
    allocation_number = db.Column(db.Integer, nullable=True, unique=True)
    status            = db.Column(db.String(20), nullable=False, default='pending')
    task_name         = db.Column(db.String(200), nullable=False)
    project_name      = db.Column(db.String(200), nullable=True)
    created_date  = db.Column(db.Date,     nullable=False)
    valid_until   = db.Column(db.Date,     nullable=False)
    usd_rate      = db.Column(db.Numeric(8, 4), nullable=False, default=3.0)
    total_nis     = db.Column(db.Numeric(14, 2), nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    items      = db.relationship('EstimateItem', backref='estimate', lazy=True,
                                  cascade='all, delete-orphan',
                                  order_by='EstimateItem.id')
    created_by = db.relationship('User', foreign_keys=[created_by_id])

    @property
    def formatted_total(self):
        if self.total_nis is None:
            return '—'
        return '{:,.2f} ₪'.format(float(self.total_nis))


class EstimateItem(db.Model):
    __tablename__ = 'estimate_items'

    id             = db.Column(db.Integer, primary_key=True)
    estimate_id    = db.Column(db.Integer, db.ForeignKey('estimates.id'), nullable=False)
    asset_id       = db.Column(db.Integer, db.ForeignKey('assets.id'),   nullable=False)
    quantity       = db.Column(db.Integer, nullable=False, default=1)
    unit_price_usd = db.Column(db.Numeric(12, 2), nullable=True)

    asset = db.relationship('Asset', foreign_keys=[asset_id])

    @property
    def line_total_nis(self):
        if not self.unit_price_usd or not self.estimate:
            return 0.0
        rate = float(self.estimate.usd_rate)
        return round(float(self.unit_price_usd) * rate * 1.7 * 1.18 * self.quantity, 2)
