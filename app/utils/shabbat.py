from datetime import datetime, time
from zoneinfo import ZoneInfo

ISRAEL_TZ   = ZoneInfo('Asia/Jerusalem')
SHABBAT_IN  = time(19, 20)
SHABBAT_OUT = time(20, 31)


def is_shabbat() -> bool:
    now     = datetime.now(ISRAEL_TZ)
    weekday = now.weekday()   # 4=Friday, 5=Saturday
    t       = now.time()
    if weekday == 4 and t >= SHABBAT_IN:
        return True
    if weekday == 5 and t < SHABBAT_OUT:
        return True
    return False
