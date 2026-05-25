import mongoengine as me

# ── Fixed pricing constants (not user-editable) ───────────────────────────────
USD_BASE_RATE: float = 3.6    # Base USD → ILS rate
BINA_FACTOR:   float = 1.048  # Conversion / Bina factor
VAT_FACTOR:    float = 1.18   # Israeli VAT

# Effective combined rate used when creating new estimates
EFFECTIVE_RATE: float = round(USD_BASE_RATE * BINA_FACTOR, 6)  # ≈ 3.7728


class AppSetting(me.Document):
    meta = {'collection': 'app_settings'}

    key   = me.StringField(max_length=100, primary_key=True)
    value = me.StringField(max_length=500, required=True)

    DEFAULTS = {'maintenance_factor': '1.7'}

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
        result = {k: float(stored.get(k, v)) for k, v in cls.DEFAULTS.items()}
        result['usd_base_rate'] = USD_BASE_RATE
        result['bina_factor']   = BINA_FACTOR
        result['vat_factor']    = VAT_FACTOR
        return result
