from datetime import datetime, timedelta

from app.models.activity import ActivityLog


def log_activity(action, description, user=None):
    """Record one activity-feed entry, then purge anything older than
    ActivityLog.RETENTION_DAYS. Runs on every call so the collection never
    grows unbounded — cheap since it's a single indexed range delete."""
    ActivityLog(
        action=action,
        description=description[:255],
        performed_by=getattr(user, 'name', None),
    ).save()

    cutoff = datetime.utcnow() - timedelta(days=ActivityLog.RETENTION_DAYS)
    ActivityLog.objects(created_at__lt=cutoff).delete()
