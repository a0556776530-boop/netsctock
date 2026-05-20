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
    for key in ('usd_rate',):
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

    # Status counts via Python (small dataset)
    status_counts = {}
    for a in Asset.objects.only('status'):
        status_counts[a.status] = status_counts.get(a.status, 0) + 1

    recent_events = list(
        AssetEvent.objects.order_by('-event_date').limit(15).select_related()
    )

    open_tasks_count = Task.objects(status__ne='done').count()

    low_stock_assets = list(
        Asset.objects(quantity__exists=True, quantity__ne=None, quantity__lt=5)
        .order_by('quantity').limit(20)
    )

    # Status chart
    all_statuses = ['in_use', 'dismantled', 'in_storage', 'assigned', 'faulty', 'retired']
    status_chart = {
        'labels': [_STATUS_LABELS[s] for s in all_statuses],
        'data':   [status_counts.get(s, 0) for s in all_statuses],
        'colors': [_STATUS_COLORS[s] for s in all_statuses],
    }

    # Type chart via Python aggregation
    type_counts = {}
    for a in Asset.objects.select_related(1):
        t_name = a.asset_type.name if a.asset_type else 'Unknown'
        type_counts[t_name] = type_counts.get(t_name, 0) + 1
    type_rows = sorted(type_counts.items(), key=lambda x: x[1], reverse=True)[:8]
    type_chart = {
        'labels': [r[0] for r in type_rows],
        'data':   [r[1] for r in type_rows],
    }

    # Activity chart: events per day last 14 days
    activity_labels, activity_data = [], []
    for i in range(13, -1, -1):
        day = today - timedelta(days=i)
        day_start = datetime.combine(day, datetime.min.time())
        day_end   = datetime.combine(day, datetime.max.time())
        count = AssetEvent.objects(
            event_date__gte=day_start, event_date__lte=day_end
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
