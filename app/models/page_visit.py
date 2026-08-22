import mongoengine as me
from datetime import datetime

# Every endpoint that counts as a meaningful page visit
PAGE_NAMES = {
    'main.dashboard':                  'לוח בקרה',
    'assets.list_assets':              'רשימת ציוד',
    'assets.list_categories':          'קטגוריות',
    'assets.detail':                   'פרטי רכיב',
    'assets.new_asset':                'יצירת רכיב חדש',
    'assets.edit':                     'עריכת רכיב',
    'tasks.list_tasks':                'משימות פתוחות',
    'tasks.history':                   'היסטוריית משימות',
    'estimates.list_estimates':        'הקצאות',
    'estimates.detail':                'פרטי הקצאה',
    'estimates.new_estimate':          'הקצאה חדשה',
    'estimates.history':               'היסטוריית הקצאות',
    'estimates.list_budget_estimates': 'הצעות מחיר',
    'estimates.warehouse_history':     'היסטוריית מחסן',
    'purchases.list_purchases':        'רכשים פעילים',
    'purchases.detail':                'פרטי רכש',
    'purchases.new_purchase':          'רכש חדש',
    'purchases.edit':                  'עריכת רכש',
    'purchases.purchase_history':      'היסטוריית רכשים',
    'purchases.receive':               'קליטת ציוד',
    'chat.app':                        "צ'אט",
    'admin.users':                     'ניהול משתמשים',
    'admin.settings':                  'הגדרות מערכת',
    'admin.login_history':             'היסטוריית כניסות',
    'admin.edit_user':                 'עריכת משתמש',
    'admin.new_user':                  'משתמש חדש',
    'pools.list_pools':                'פולים',
    'auth.change_password':            'שינוי סיסמה',
}


class PageVisit(me.Document):
    meta = {
        'collection': 'page_visits',
        'ordering': ['-visited_at'],
        'index_background': True,
        'indexes': [
            ('user_id', '-visited_at'),
            '-visited_at',
            {'fields': ['visited_at'], 'expireAfterSeconds': 60 * 60 * 24 * 90},  # TTL 90 days
        ],
    }

    user_id    = me.StringField(required=True, max_length=50)
    user_name  = me.StringField(max_length=150)
    user_role  = me.StringField(max_length=50)
    path       = me.StringField(max_length=500)
    page_name  = me.StringField(max_length=200)
    visited_at = me.DateTimeField(default=datetime.utcnow)
    ip_address = me.StringField(max_length=60)
    session_id = me.StringField(max_length=40)
