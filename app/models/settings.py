import mongoengine as me


class AppSetting(me.Document):
    meta = {'collection': 'app_settings'}

    key   = me.StringField(max_length=100, primary_key=True)
    value = me.StringField(max_length=500, required=True)

    DEFAULTS = {'usd_rate': '3.0'}

    @classmethod
    def get(cls, key):
        row = cls.objects(key=key).first()
        return float(row.value if row else cls.DEFAULTS.get(key, '0'))

    @classmethod
    def set(cls, key, value):
        row = cls.objects(key=key).first()
        if row:
            row.value = str(value)
            row.save()
        else:
            cls(key=key, value=str(value)).save()

    @classmethod
    def all_as_dict(cls):
        stored = {r.key: r.value for r in cls.objects}
        return {k: float(stored.get(k, v)) for k, v in cls.DEFAULTS.items()}
