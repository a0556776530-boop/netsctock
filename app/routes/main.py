import json
from datetime import date, timedelta, datetime

from flask import Blueprint, render_template, jsonify, redirect, request, session, url_for
from flask_login import login_required
from sqlalchemy import func

from app import db
from app.models.asset import Asset, AssetEvent, AssetType
from app.models.task import Task

main_bp = Blueprint('main', __name__)

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


@main_bp.route('/set-lang/<code>')
def set_lang(code):
    if code in ('en', 'he'):
        session['lang'] = code
        session.permanent = True
    return redirect(request.referrer or url_for('main.dashboard'))


@main_bp.route('/api/rate')
@login_required
def exchange_rate():
    from app.utils.exchange import get_usd_to_nis
    rate = get_usd_to_nis()
    return jsonify({'rate': rate, 'base': 'USD', 'target': 'ILS'})


@main_bp.route('/api/settings', methods=['GET'])
@login_required
def get_settings():
    from app.models.settings import AppSetting
    return jsonify(AppSetting.all_as_dict())


@main_bp.route('/api/settings', methods=['POST'])
@login_required
def save_settings():
    from app.models.settings import AppSetting
    data = request.get_json(silent=True) or {}
    allowed = ('usd_rate', 'conversion_fee', 'bynet_factor')
    for key in allowed:
        if key in data:
            try:
                AppSetting.set(key, float(data[key]))
            except (ValueError, TypeError):
                pass
    db.session.commit()
    return jsonify({'ok': True})


@main_bp.route('/')
@login_required
def dashboard():
    today = date.today()

    total_assets = Asset.query.count()
    status_counts = dict(
        db.session.query(Asset.status, func.count(Asset.id))
        .group_by(Asset.status).all()
    )

    recent_events = (
        AssetEvent.query.order_by(AssetEvent.event_date.desc()).limit(15).all()
    )

    open_tasks_count = Task.query.filter(Task.status != 'done').count()

    low_stock_assets = Asset.query.filter(
        Asset.quantity != None, Asset.quantity < 5
    ).order_by(Asset.quantity.asc()).limit(20).all()

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
        recent_events=recent_events,
        open_tasks_count=open_tasks_count,
        low_stock_assets=low_stock_assets,
        today=today,
        status_chart=json.dumps(status_chart),
        type_chart=json.dumps(type_chart),
        activity_chart=json.dumps(activity_chart),
    )
