import mongoengine as me
from datetime import datetime


class PoolTransaction(me.EmbeddedDocument):
    estimate      = me.ReferenceField('Estimate')
    amount_drawn  = me.FloatField(required=True)
    currency      = me.StringField()
    exchange_rate = me.FloatField()
    created_at    = me.DateTimeField(default=datetime.utcnow)
    created_by    = me.ReferenceField('User')
    notes         = me.StringField()

    @property
    def estimate_display(self):
        try:
            e = self.estimate
            num = f'#{e.allocation_number} — ' if e.allocation_number else ''
            return {'id': str(e.id), 'label': f'{num}{e.task_name}', 'project': e.project_name or '—', 'deleted': False}
        except Exception:
            return {'id': None, 'label': 'הקצאה נמחקה', 'project': '—', 'deleted': True}


class Pool(me.Document):
    meta = {
        'collection': 'pools',
        'indexes': ['emf_number', '-created_at'],
    }

    name            = me.StringField(max_length=200, required=True)
    emf_number      = me.StringField(max_length=50, required=True, unique=True, sparse=True)
    total_amount    = me.FloatField(required=True)
    consumed_amount = me.FloatField(default=0.0)
    currency        = me.StringField(default='ILS')   # 'ILS' | 'USD'
    notes           = me.StringField()
    created_at      = me.DateTimeField(default=datetime.utcnow)
    created_by      = me.ReferenceField('User')
    transactions    = me.EmbeddedDocumentListField(PoolTransaction)

    @property
    def balance(self):
        return round(self.total_amount - self.consumed_amount, 2)

    @property
    def balance_pct(self):
        if not self.total_amount:
            return 0
        return min(100, round((self.consumed_amount / self.total_amount) * 100, 1))

    @property
    def symbol(self):
        return '₪' if self.currency == 'ILS' else '$'

    def fmt(self, amount):
        if self.currency == 'ILS':
            return '₪{:,.0f}'.format(amount)
        return '${:,.2f}'.format(amount)
