import mongoengine as me
from datetime import datetime


class AssetType(me.Document):
    meta = {'collection': 'asset_types'}

    name     = me.StringField(max_length=100, required=True)
    category = me.StringField(max_length=100)

    def __repr__(self):
        return f'<AssetType {self.name}>'


class Asset(me.Document):
    meta = {
        'collection': 'assets',
        'strict': False,
        'indexes': ['status', 'quantity', 'serial_number', 'component_id'],
    }

    STATUSES = ['in_use', 'dismantled', 'in_storage', 'assigned', 'faulty', 'retired']
    STATUS_LABELS = {
        'in_use': 'בשימוש', 'dismantled': 'פורק', 'in_storage': 'באחסון',
        'assigned': 'מוקצה', 'faulty': 'פגום', 'retired': 'מחיקת פריט',
    }
    STATUS_COLORS = {
        'in_use': 'success', 'dismantled': 'warning', 'in_storage': 'info',
        'assigned': 'primary', 'faulty': 'danger', 'retired': 'secondary',
    }

    component_id   = me.StringField(max_length=50)
    serial_number  = me.StringField(max_length=100, required=True, unique=True, sparse=True)
    barcode        = me.StringField(max_length=100, sparse=True)
    asset_type     = me.ReferenceField('AssetType', db_field='asset_type_id')
    model          = me.StringField(max_length=150)
    manufacturer   = me.StringField(max_length=150)
    status         = me.StringField(default='in_storage', choices=STATUSES)
    current_site   = me.ReferenceField('Site', db_field='current_site_id')
    assignee       = me.ReferenceField('User', db_field='assigned_to_id')
    notes          = me.StringField()
    price          = me.FloatField()
    price_nis      = me.FloatField()
    price_usd      = me.FloatField()
    conversion_fee = me.FloatField()
    quantity       = me.IntField()
    min_threshold  = me.IntField()
    created_at     = me.DateTimeField(default=datetime.utcnow)
    updated_at     = me.DateTimeField(default=datetime.utcnow)

    def __repr__(self):
        return f'<Asset {self.serial_number}>'

    @property
    def status_label(self):
        return self.STATUS_LABELS.get(self.status, self.status)

    @property
    def status_color(self):
        return self.STATUS_COLORS.get(self.status, 'secondary')

    def _safe_ref(self, field):
        try:
            return getattr(self, field)
        except Exception:
            return None

    @property
    def safe_assignee(self):
        return self._safe_ref('assignee')

    @property
    def safe_current_site(self):
        return self._safe_ref('current_site')

    @property
    def safe_asset_type(self):
        return self._safe_ref('asset_type')


class AssetEvent(me.Document):
    meta = {
        'collection': 'asset_events',
        'ordering': ['-event_date'],
        'indexes': ['-event_date'],
    }

    EVENT_TYPES = ['dismantled', 'moved', 'assigned', 'returned', 'repaired',
                   'created', 'retired', 'status_change']
    EVENT_LABELS = {
        'dismantled': 'פורק', 'moved': 'הועבר', 'assigned': 'הוקצה',
        'returned': 'הוחזר', 'repaired': 'תוקן', 'created': 'נוצר',
        'retired': 'הוצא משירות', 'status_change': 'סטטוס שונה',
    }
    EVENT_ICONS = {
        'dismantled': 'bi-tools', 'moved': 'bi-arrow-left-right',
        'assigned': 'bi-person-check', 'returned': 'bi-arrow-return-left',
        'repaired': 'bi-wrench', 'created': 'bi-plus-circle',
        'retired': 'bi-archive', 'status_change': 'bi-arrow-repeat',
    }

    asset             = me.ReferenceField('Asset', required=True, db_field='asset_id')
    event_type        = me.StringField(required=True)
    from_site         = me.ReferenceField('Site', db_field='from_site_id')
    to_site           = me.ReferenceField('Site', db_field='to_site_id')
    performed_by_user = me.ReferenceField('User', required=True, db_field='performed_by_id')
    notes             = me.StringField()
    event_date        = me.DateTimeField(default=datetime.utcnow)

    def __repr__(self):
        return f'<AssetEvent {self.event_type}>'

    def _safe_ref(self, field):
        try:
            return getattr(self, field)
        except Exception:
            return None

    @property
    def performer_name(self):
        try:
            return self.performed_by_user.name if self.performed_by_user else '—'
        except Exception:
            return '—'

    @property
    def safe_from_site(self):
        return self._safe_ref('from_site')

    @property
    def safe_to_site(self):
        return self._safe_ref('to_site')

    @property
    def safe_asset(self):
        return self._safe_ref('asset')

    @property
    def event_label(self):
        return self.EVENT_LABELS.get(self.event_type, self.event_type)

    @property
    def event_icon(self):
        return self.EVENT_ICONS.get(self.event_type, 'bi-circle')
