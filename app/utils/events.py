from app.models.asset import AssetEvent
from datetime import datetime


def log_event(asset, event_type, performed_by, from_site=None, to_site=None, notes=None):
    event = AssetEvent(
        asset=asset,
        event_type=event_type,
        from_site=from_site,
        to_site=to_site,
        performed_by_user=performed_by,
        notes=notes,
        event_date=datetime.utcnow(),
    )
    event.save()
