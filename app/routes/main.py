import json
from datetime import date, timedelta, datetime

from flask import Blueprint, render_template, jsonify, redirect, request, session, url_for
from flask_login import login_required

from app.models.asset import Asset, AssetEvent, AssetType
from app.models.task import Task

main_bp = Blueprint('main', __name__)

_STATUS_COLORS = {
    'in_use': '#198754', 'dismantled': '#ffc107', 'in_storage': '#0dcaf0',
    'assigned': '#0d6efd', 'faulty': '#dc3545', 'retired': '#adb5bd',
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
    for key in ('usd_rate', 'maintenance_factor'):
        if key in data:
            try:
                AppSetting.set(key, float(data[key]))
            except (ValueError, TypeError):
                pass
    return jsonify({'ok': True})


@main_bp.route('/')
@login_required
def dashboard():
    today = date.today()

    total_assets = Asset.objects.count()

    # Status counts — MongoDB aggregation (no Python-side loading)
    pipeline_status = [{'$group': {'_id': '$status', 'count': {'$sum': 1}}}]
    status_counts = {r['_id']: r['count'] for r in Asset._get_collection().aggregate(pipeline_status) if r['_id']}

    # Recent events — limit fields fetched
    recent_events = list(
        AssetEvent.objects.order_by('-event_date').limit(10).select_related(max_depth=1)
    )

    open_tasks_count = Task.objects(status__ne='done').count()

    low_stock_assets = list(
        Asset.objects(quantity__exists=True, quantity__ne=None, quantity__lt=5)
        .only('component_id', 'serial_number', 'model', 'quantity', 'min_threshold')
        .order_by('quantity').limit(10)
    )

    # Status chart
    all_statuses = ['in_use', 'dismantled', 'in_storage', 'assigned', 'faulty', 'retired']
    status_chart = {
        'labels': [_STATUS_LABELS[s] for s in all_statuses],
        'data':   [status_counts.get(s, 0) for s in all_statuses],
        'colors': [_STATUS_COLORS[s] for s in all_statuses],
    }

    # Type chart — MongoDB aggregation via lookup
    pipeline_type = [
        {'$group': {'_id': '$asset_type_id', 'count': {'$sum': 1}}},
        {'$lookup': {'from': 'asset_types', 'localField': '_id', 'foreignField': '_id', 'as': 'type_info'}},
        {'$sort': {'count': -1}},
        {'$limit': 8},
    ]
    type_rows = []
    for r in Asset._get_collection().aggregate(pipeline_type):
        name = r['type_info'][0]['name'] if r.get('type_info') else 'Unknown'
        type_rows.append((name, r['count']))
    type_chart = {
        'labels': [r[0] for r in type_rows],
        'data':   [r[1] for r in type_rows],
    }

    # Activity chart — one aggregation instead of 14 queries
    from datetime import timezone
    day_start_14 = datetime.combine(today - timedelta(days=13), datetime.min.time())
    pipeline_activity = [
        {'$match': {'event_date': {'$gte': day_start_14}}},
        {'$group': {'_id': {'$dateToString': {'format': '%Y-%m-%d', 'date': '$event_date'}}, 'count': {'$sum': 1}}},
    ]
    activity_by_day = {r['_id']: r['count'] for r in AssetEvent._get_collection().aggregate(pipeline_activity)}
    activity_labels, activity_data = [], []
    for i in range(13, -1, -1):
        day = today - timedelta(days=i)
        activity_labels.append(day.strftime('%d %b'))
        activity_data.append(activity_by_day.get(day.strftime('%Y-%m-%d'), 0))
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
