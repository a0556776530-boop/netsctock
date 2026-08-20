import mongoengine as me
from datetime import datetime


class EstimateItem(me.EmbeddedDocument):
    asset          = me.ReferenceField('Asset')
    quantity       = me.IntField(default=1)
    unit_price_usd = me.FloatField()

    @property
    def safe_asset(self):
        try:
            return self.asset
        except Exception:
            return None

    def line_total_nis(self, usd_rate, maintenance_factor=1.7):
        if not self.unit_price_usd:
            return 0.0
        return round(self.unit_price_usd * float(usd_rate) * maintenance_factor * 1.18 * self.quantity, 2)


class Estimate(me.Document):
    meta = {
        'collection': 'estimates',
        'index_background': True,
        'indexes': [
            'status',
            'record_type',
            'warehouse_status',
            'allocation_number',
            '-created_at',
            ('status', 'record_type'),
            ('status', 'record_type', 'valid_until'),
        ],
    }

    allocation_number  = me.IntField(unique=True, sparse=True)
    status             = me.StringField(default='pending')
    record_type        = me.StringField(default='allocation')
    warehouse_status   = me.StringField(default='pending')
    warehouse_completed_at = me.DateTimeField()
    task_name          = me.StringField(max_length=200, required=True)
    project_name       = me.StringField(max_length=200)
    created_date       = me.DateField()
    valid_until        = me.DateField()
    usd_rate           = me.FloatField(default=3.0)
    maintenance_factor = me.FloatField(default=1.7)
    total_nis          = me.FloatField()
    total_usd          = me.FloatField()   # stored so list view doesn't need items
    created_by         = me.ReferenceField('User')
    created_at         = me.DateTimeField(default=datetime.utcnow)
    withdrawn_at       = me.DateTimeField()

    pool  = me.ReferenceField('Pool', null=True)
    items = me.EmbeddedDocumentListField(EstimateItem)

    @property
    def formatted_total_usd(self):
        v = self.total_usd
        if v is None:
            # fallback: compute from items (only if items are loaded)
            try:
                v = sum((item.unit_price_usd or 0) * item.quantity for item in self.items)
            except Exception:
                return '—'
        return '${:,.2f}'.format(v) if v else '—'

    @property
    def formatted_total(self):
        if self.total_nis is None:
            return '—'
        return '{:,.2f} ₪'.format(float(self.total_nis))
