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
    meta = {'collection': 'estimates'}

    allocation_number  = me.IntField(unique=True, sparse=True)
    status             = me.StringField(default='pending')
    task_name          = me.StringField(max_length=200, required=True)
    project_name       = me.StringField(max_length=200)
    created_date       = me.DateField()
    valid_until        = me.DateField()
    usd_rate           = me.FloatField(default=3.0)
    maintenance_factor = me.FloatField(default=1.7)
    total_nis          = me.FloatField()
    created_by         = me.ReferenceField('User')
    created_at         = me.DateTimeField(default=datetime.utcnow)
    withdrawn_at       = me.DateTimeField()

    items = me.EmbeddedDocumentListField(EstimateItem)

    @property
    def total_usd(self):
        return sum((item.unit_price_usd or 0) * item.quantity for item in self.items)

    @property
    def formatted_total_usd(self):
        t = self.total_usd
        return '${:,.2f}'.format(t) if t else '—'

    @property
    def formatted_total(self):
        if self.total_nis is None:
            return '—'
        return '{:,.2f} ₪'.format(float(self.total_nis))
