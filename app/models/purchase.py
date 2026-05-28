import mongoengine as me
from datetime import datetime


STATUSES = [
    'BOM Transferred',
    'Requirement Created',
    'Order Signed',
    'Order Received in Warehouse',
]

CURRENCIES = ['ILS', 'USD Aid', 'USD Cash']

STATUS_COLORS = {
    'BOM Transferred':             'secondary',
    'Requirement Created':         'info',
    'Order Signed':                'primary',
    'Order Received in Warehouse': 'success',
}


class PurchaseItem(me.EmbeddedDocument):
    asset      = me.ReferenceField('Asset', required=True)
    quantity   = me.IntField(required=True)
    unit_price = me.FloatField(default=0)


class Purchase(me.Document):
    meta = {'collection': 'purchases', 'ordering': ['-created_at']}

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

    @property
    def status_color(self):
        return STATUS_COLORS.get(self.status, 'secondary')

    @property
    def total_price(self):
        return sum((i.unit_price or 0) * (i.quantity or 0) for i in self.items)
