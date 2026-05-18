from app import db


class AppSetting(db.Model):
    __tablename__ = 'app_settings'

    key   = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.String(500), nullable=False)

    # ── Defaults ──────────────────────────────────────────────────────────────
    DEFAULTS = {
        'usd_rate': '3.0',
    }

    @classmethod
    def get(cls, key):
        row = cls.query.get(key)
        return float(row.value if row else cls.DEFAULTS.get(key, '0'))

    @classmethod
    def set(cls, key, value):
        row = cls.query.get(key)
        if row:
            row.value = str(value)
        else:
            db.session.add(cls(key=key, value=str(value)))

    @classmethod
    def all_as_dict(cls):
        stored = {r.key: r.value for r in cls.query.all()}
        return {k: float(stored.get(k, v)) for k, v in cls.DEFAULTS.items()}
