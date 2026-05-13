import json
from datetime import date, timedelta, datetime

from flask import Blueprint, render_template
from flask_login import login_required
from sqlalchemy import func

from app import db
from app.models.asset import Asset, AssetEvent, AssetType
from app.models.task import Task

main_bp = Blueprint('main', __name__)

# Bootstrap colour map (background hex)
_STATUS_COLORS = {
    'in_use':     '#198754',
    'dismantled': '#ffc107',
    'in_storage': '#0dcaf0',
    'assigned':   '#0d6efd',
    'faulty':     '#dc3545',
    'retired':    '#adb5bd',
}
_STATUS_LABELS = {
    'in_use': 'In Use', 'dismantled': 'Dismantled', 'in_storage': 'In Storage',
    'assigned': 'Assigned', 'faulty': 'Faulty', 'retired': 'Retired',
}


@main_bp.route('/')
@login_required
def dashboard():
    today = date.today()
    soon  = today + timedelta(days=7)

    # ── Core counts ───────────────────────────────────────────────────────────
    total_assets = Asset.query.count()
    status_counts = dict(
        db.session.query(Asset.status, func.count(Asset.id))
        .group_by(Asset.status).all()
    )

    overdue_assets = Asset.query.filter(
        Asset.due_date < today, Asset.status != 'retired'
    ).order_by(Asset.due_date).limit(10).all()

    due_soon_assets = Asset.query.filter(
        Asset.due_date >= today, Asset.due_date <= soon, Asset.status != 'retired'
    ).order_by(Asset.due_date).limit(10).all()

    recent_events = (
        AssetEvent.query.order_by(AssetEvent.event_date.desc()).limit(15).all()
    )

    overdue_tasks = Task.query.filter(
        Task.due_date < today, Task.status != 'done'
    ).order_by(Task.due_date).limit(10).all()

    # ── Chart: assets by status (doughnut) ───────────────────────────────────
    all_statuses = ['in_use', 'dismantled', 'in_storage', 'assigned', 'faulty', 'retired']
    status_chart = {
        'labels': [_STATUS_LABELS[s] for s in all_statuses],
        'data':   [status_counts.get(s, 0) for s in all_statuses],
        'colors': [_STATUS_COLORS[s] for s in all_statuses],
    }

    # ── Chart: top asset types (horizontal bar) ───────────────────────────────
    type_rows = (
        db.session.query(AssetType.name, func.count(Asset.id))
        .outerjoin(Asset, Asset.asset_type_id == AssetType.id)
        .group_by(AssetType.name)
        .order_by(func.count(Asset.id).desc())
        .limit(8).all()
    )
    type_chart = {
        'labels': [r[0] for r in type_rows],
        'data':   [r[1] for r in type_rows],
    }

    # ── Chart: events per day — last 14 days (line) ───────────────────────────
    activity_labels, activity_data = [], []
    for i in range(13, -1, -1):
        day = today - timedelta(days=i)
        day_start = datetime.combine(day, datetime.min.time())
        day_end   = datetime.combine(day, datetime.max.time())
        count = AssetEvent.query.filter(
            AssetEvent.event_date >= day_start,
            AssetEvent.event_date <= day_end,
        ).count()
        activity_labels.append(day.strftime('%d %b'))
        activity_data.append(count)

    activity_chart = {'labels': activity_labels, 'data': activity_data}

    return render_template(
        'dashboard.html',
        total_assets=total_assets,
        status_counts=status_counts,
        overdue_assets=overdue_assets,
        due_soon_assets=due_soon_assets,
        recent_events=recent_events,
        overdue_tasks=overdue_tasks,
        today=today,
        status_chart=json.dumps(status_chart),
        type_chart=json.dumps(type_chart),
        activity_chart=json.dumps(activity_chart),
    )
