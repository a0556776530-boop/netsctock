import mongoengine as me
from datetime import datetime


STATUSES = [
    'BOM Transferred',
    'Requirement Created',
    'Order Signed',
    'Partial Delivery',
    'Order Received in Warehouse',
    'בוטל',
]

ACTIVE_STATUSES = [
    'BOM Transferred',
    'Requirement Created',
    'Order Signed',
    'Partial Delivery',
]

# Statuses available for manual selection — Partial Delivery is set automatically only
MANUAL_STATUSES = [s for s in STATUSES if s != 'Partial Delivery']

CURRENCIES = ['ILS', 'USD Aid', 'USD Cash']

STATUS_COLORS = {
    'BOM Transferred':             'secondary',
    'Requirement Created':         'info',
    'Order Signed':                'primary',
    'Partial Delivery':            'warning',
    'Order Received in Warehouse': 'success',
    'בוטל':                        'danger',
}


class PurchaseItem(me.EmbeddedDocument):
    meta = {'strict': False}

    asset        = me.ReferenceField('Asset', required=True)
    quantity     = me.IntField(required=True)
    unit_price   = me.FloatField(default=0)
    received_qty = me.IntField(default=0)

    @property
    def safe_asset(self):
        try:
            return self.asset
        except Exception:
            return None

    @property
    def remaining_qty(self):
        return max(0, (self.quantity or 0) - (self.received_qty or 0))

    @property
    def is_fully_received(self):
        return (self.received_qty or 0) >= (self.quantity or 0)


class Purchase(me.Document):
    meta = {
        'collection': 'purchases',
        'ordering': ['-created_at'],
        'strict': False,
        'index_background': True,
        'indexes': [
            '-created_at',
            ('status', '-created_at'),  # list/history pages: filter by status + sort by date
        ],
    }

    name            = me.StringField(required=True, max_length=200)
    bom_date        = me.DateTimeField()
    estimate_number = me.StringField(max_length=200)
    amount          = me.FloatField()
    currency        = me.StringField(choices=CURRENCIES, default='ILS')
    emf             = me.StringField(max_length=200)
    requirement     = me.StringField(max_length=200)
    order           = me.StringField(max_length=200)
    status          = me.StringField(choices=STATUSES, default='BOM Transferred')
    bom_file        = me.StringField()
    items           = me.EmbeddedDocumentListField(PurchaseItem)
    created_at      = me.DateTimeField(default=datetime.utcnow)
    received_at     = me.DateTimeField()   # set atomically on first receipt sync

    @property
    def status_color(self):
        return STATUS_COLORS.get(self.status, 'secondary')

    @property
    def total_price(self):
        return sum((i.unit_price or 0) * (i.quantity or 0) for i in self.items)

    @property
    def delivery_progress(self):
        items = [i for i in self.items if i.safe_asset]
        total    = sum(i.quantity or 0 for i in items)
        received = sum(i.received_qty or 0 for i in items)
        return (received, total)
