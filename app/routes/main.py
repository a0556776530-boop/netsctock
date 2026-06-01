import json
from datetime import date, timedelta, datetime

from flask import Blueprint, render_template, jsonify, redirect, request, session, url_for
from flask_login import login_required, current_user

from app.models.asset import Asset, AssetEvent, AssetType
from app.models.task import Task

main_bp = Blueprint('main', __name__)

_STATUS_COLORS = {
    'in_use': '#198754', 'dismantled': '#ffc107', 'in_storage': '#0dcaf0',
    'assigned': '#0d6efd', 'faulty': '#dc3545', 'retired': '#adb5bd',
}
_STATUS_LABELS = {
    'in_use': 'In Use', 'dismantled': 'Dismantled', 'in_storage': 'In Storage',
    'assigned': 'Assigned', 'faulty': 'Faulty', 'retired': 'Deleted',
}


@main_bp.route('/set-lang/<code>')
def set_lang(code):
    if code in ('en', 'he'):
        session['lang'] = code
        session.permanent = True
    return redirect(request.referrer or url_for('main.dashboard'))


@main_bp.route('/api/ping')
@login_required
def ping():
    return jsonify({'ok': True})


@main_bp.route('/api/user-activity')
@login_required
def user_activity_api():
    if not current_user.is_admin:
        return jsonify({'ok': False}), 403
    from app.models.user import User
    now_utc = datetime.utcnow()
    result = []
    for u in User.objects.order_by('-last_seen'):
        if u.last_seen:
            diff = (now_utc - u.last_seen).total_seconds()
            if diff < 300:
                status = 'online'
            elif diff < 1800:
                status = 'away'
            else:
                status = 'offline'
            diff_min = int(diff / 60)
            diff_sec = int(diff)
        else:
            status = 'never'
            diff_min = None
            diff_sec = None
        result.append({
            'id':         str(u.id),
            'name':       u.name,
            'role':       u.role,
            'status':     status,
            'diff_sec':   diff_sec,
            'diff_min':   diff_min,
            'last_login': u.last_login.strftime('%d %b') if u.last_login else None,
        })
    return jsonify({'ok': True, 'users': result, 'now': now_utc.isoformat()})


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
    if not current_user.can_edit:
        return jsonify({'ok': False, 'error': 'Forbidden'}), 403
    from app.models.settings import AppSetting
    data = request.get_json(silent=True) or {}
    for key in ('maintenance_factor', 'usd_base_rate', 'bina_factor', 'vat_factor'):
        if key in data:
            try:
                val = float(data[key])
                if val > 0:
                    AppSetting.set(key, val)
            except (ValueError, TypeError):
                pass
    return jsonify({'ok': True})


@main_bp.route('/')
@login_required
def dashboard():
    if current_user.is_warehouse:
        return redirect(url_for('estimates.list_estimates'))
    from mongoengine import Q
    from app.models.estimate import Estimate
    from app.models.purchase import Purchase
    from app.models.user import User

    today = date.today()

    # ── Core counts ───────────────────────────────────────────────────────────
    total_assets = Asset.objects.count()
    open_tasks_count = Task.objects(status__ne='done').count()
    pending_allocations_count = Estimate.objects(
        Q(status='pending') & Q(record_type__ne='estimate')
    ).count()
    open_purchases_count = Purchase.objects(
        status__ne='Order Received in Warehouse'
    ).count()

    # ── Status counts ─────────────────────────────────────────────────────────
    pipeline_status = [{'$group': {'_id': '$status', 'count': {'$sum': 1}}}]
    status_counts = {r['_id']: r['count'] for r in Asset._get_collection().aggregate(pipeline_status) if r['_id']}

    # ── Recent events ─────────────────────────────────────────────────────────
    recent_events = []
    for event in AssetEvent.objects.order_by('-event_date').limit(50).select_related(max_depth=1):
        try:
            _ = event.performed_by_user.name
            _ = event.asset.serial_number
            recent_events.append(event)
        except Exception:
            continue
        if len(recent_events) >= 8:
            break

    # ── Low stock (respects min_threshold) ───────────────────────────────────
    low_stock_assets = []
    for a in Asset.objects(quantity__exists=True, quantity__ne=None).only(
        'component_id', 'serial_number', 'model', 'quantity', 'min_threshold', 'price_usd'
    ).order_by('quantity').limit(50):
        threshold = a.min_threshold if a.min_threshold else 5
        if (a.quantity or 0) < threshold:
            low_stock_assets.append(a)
        if len(low_stock_assets) >= 10:
            break

    # ── Expiring allocations (expired or within 14 days) ─────────────────────
    cutoff = today + timedelta(days=7)
    expiring_estimates = list(
        Estimate.objects(
            Q(status='pending') & Q(record_type__ne='estimate') & Q(valid_until__lte=cutoff)
        ).order_by('valid_until').limit(8)
    )

    # ── Purchases by status (pipeline) ───────────────────────────────────────
    from app.models.purchase import STATUSES as PURCHASE_STATUSES
    _p_agg = Purchase._get_collection().aggregate([{'$group': {'_id': '$status', 'count': {'$sum': 1}}}])
    purchase_status_counts = {r['_id']: r['count'] for r in _p_agg if r['_id']}
    purchases_pipeline = [(s, purchase_status_counts.get(s, 0)) for s in PURCHASE_STATUSES]

    # ── Top committed assets (server-side aggregation) ────────────────────────
    _commit_pipeline = [
        {'$match': {'status': 'pending', 'record_type': {'$ne': 'estimate'}}},
        {'$unwind': '$items'},
        {'$match': {'items.asset': {'$exists': True, '$ne': None}}},
        {'$group': {'_id': '$items.asset', 'committed': {'$sum': '$items.quantity'}}},
        {'$sort': {'committed': -1}},
        {'$limit': 6},
    ]
    top_committed = []
    for row in Estimate._get_collection().aggregate(_commit_pipeline):
        asset = Asset.objects(id=row['_id']).only('serial_number', 'model', 'quantity', 'component_id').first()
        if asset:
            top_committed.append({'asset': asset, 'committed': row['committed']})

    # ── Users activity ───────────────────────────────────────────────────────
    now_utc = datetime.utcnow()
    all_users = []
    for u in User.objects.order_by('-last_seen'):
        if u.last_seen:
            diff = (now_utc - u.last_seen).total_seconds()
            if diff < 300:
                status = 'online'
            elif diff < 1800:
                status = 'away'
            else:
                status = 'offline'
            diff_min = int(diff / 60)
        else:
            status = 'never'
            diff_min = None
        all_users.append({'user': u, 'status': status, 'diff_min': diff_min})

    # ── Charts ────────────────────────────────────────────────────────────────
    all_statuses = ['in_use', 'dismantled', 'in_storage', 'assigned', 'faulty', 'retired']
    status_chart = {
        'labels': [_STATUS_LABELS[s] for s in all_statuses],
        'data':   [status_counts.get(s, 0) for s in all_statuses],
        'colors': [_STATUS_COLORS[s] for s in all_statuses],
    }

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
        pending_allocations_count=pending_allocations_count,
        open_purchases_count=open_purchases_count,
        low_stock_assets=low_stock_assets,
        expiring_estimates=expiring_estimates,
        purchases_pipeline=purchases_pipeline,
        top_committed=top_committed,
        all_users=all_users,
        now_utc=now_utc,
        today=today,
        status_chart=json.dumps(status_chart),
        activity_chart=json.dumps(activity_chart),
    )
