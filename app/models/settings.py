import time
import mongoengine as me

_cache: dict = {}  # key -> (value, expires_at)
_TTL = 60  # seconds

# Fallback defaults — user can override these via the UI (stored in AppSetting)
USD_BASE_RATE: float = 3.6
BINA_FACTOR:   float = 1.048
VAT_FACTOR:    float = 1.18
EFFECTIVE_RATE: float = round(USD_BASE_RATE * BINA_FACTOR, 6)


class AppSetting(me.Document):
    meta = {'collection': 'app_settings'}

    key   = me.StringField(max_length=100, primary_key=True)
    value = me.StringField(max_length=500, required=True)

    DEFAULTS = {
        'maintenance_factor': '1.7',
        'usd_base_rate':      str(USD_BASE_RATE),
        'bina_factor':        str(BINA_FACTOR),
        'vat_factor':         str(VAT_FACTOR),
    }

    @classmethod
    def get(cls, key):
        now = time.time()
        if key in _cache:
            val, exp = _cache[key]
            if now < exp:
                return val
        row = cls.objects(key=key).first()
        val = float(row.value if row else cls.DEFAULTS.get(key, '0'))
        _cache[key] = (val, now + _TTL)
        return val

    @classmethod
    def set(cls, key, value):
        row = cls.objects(key=key).first()
        if row:
            row.value = str(value)
            row.save()
        else:
            cls(key=key, value=str(value)).save()
        _cache.pop(key, None)  # invalidate

    @classmethod
    def all_as_dict(cls):
        stored = {r.key: r.value for r in cls.objects}
        return {k: float(stored.get(k, v)) for k, v in cls.DEFAULTS.items()}
