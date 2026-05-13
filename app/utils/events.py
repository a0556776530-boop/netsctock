from app import db
from app.models.asset import AssetEvent
from datetime import datetime


def log_event(asset, event_type, performed_by, from_site=None, to_site=None, notes=None):
    event = AssetEvent(
        asset_id=asset.id,
        event_type=event_type,
        from_site_id=from_site.id if from_site else None,
        to_site_id=to_site.id if to_site else None,
        performed_by_id=performed_by.id,
        notes=notes,
        event_date=datetime.utcnow(),
    )
    db.session.add(event)
