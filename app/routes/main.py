import json
import types
from datetime import date, timedelta, datetime
from urllib.parse import urlparse

from flask import Blueprint, render_template, jsonify, redirect, request, session, url_for, send_from_directory
import os as _os
from flask_login import login_required, current_user
from app.utils.cache import cache

from app.models.asset import Asset
from app.models.task import Task

main_bp = Blueprint('main', __name__)

_STATUS_COLORS = {
    'in_use': '#198754', 'in_storage': '#0dcaf0',
    'assigned': '#0d6efd', 'faulty': '#dc3545',
}
_STATUS_LABELS = {
    'in_use': 'In Use', 'in_storage': 'In Storage',
    'assigned': 'Assigned', 'faulty': 'Faulty',
}


@main_bp.route('/sw.js')
def service_worker():
    from flask import current_app
    resp = send_from_directory(
        _os.path.join(current_app.root_path, 'static', 'js'),
        'sw.js',
        mimetype='application/javascript'
    )
    resp.headers['Service-Worker-Allowed'] = '/'
    resp.headers['Cache-Control'] = 'no-cache'
    return resp


@main_bp.route('/set-lang/<code>')
def set_lang(code):
    if code in ('en', 'he'):
        session['lang'] = code
        session.permanent = True
    # Extract only the path from the Referer to prevent open-redirect via a
    # spoofed Referer header pointing to an external host.
    ref = request.referrer or ''
    safe_back = urlparse(ref).path or url_for('main.dashboard')
    return redirect(safe_back)


@main_bp.route('/api/ping')
@login_required
def ping():
    from datetime import datetime
    from app.models.user import User
    now = datetime.utcnow()
    ls  = current_user.last_seen
    if ls is None or (now - ls).total_seconds() > 15:
        User.objects(id=current_user.id).update_one(set__last_seen=now)
        current_user.last_seen = now
    return jsonify({'ok': True})




@main_bp.route('/api/user-activity')
@login_required
def user_activity_api():
    if not current_user.is_admin:
        return jsonify({'ok': False}), 403
    _hit = cache.get('user_activity_api')
    if _hit is not None:
        return jsonify(_hit)
    from app.models.user import User
    now_utc = datetime.utcnow()
    result = []
    for u in User.objects.order_by('-last_seen').only('id', 'name', 'role', 'last_seen', 'last_login'):
        if u.last_seen:
            diff = (now_utc - u.last_seen).total_seconds()
            if diff < 35:
                status = 'online'
            elif diff < 600:
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
            'last_seen_utc': u.last_seen.strftime('%H:%M:%S') if u.last_seen else None,
        })
    payload = {'ok': True, 'users': result, 'now': now_utc.isoformat()}
    cache.set('user_activity_api', payload, timeout=10)
    return jsonify(payload)


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



@cache.memoize(timeout=45)
def _expiring_estimates():
    from mongoengine import Q
    from app.models.estimate import Estimate
    from datetime import date, timedelta
    today = date.today()
    cutoff = today + timedelta(days=7)
    return list(Estimate.objects(
        Q(status='pending') & Q(record_type__ne='estimate') & Q(valid_until__lte=cutoff)
    ).order_by('valid_until').limit(8))


@cache.memoize(timeout=60)
def _dashboard_data():
    """All heavy dashboard computations — cached 60s, returns primitive types only."""
    from mongoengine import Q
    from app.models.estimate import Estimate
    from app.models.purchase import Purchase, ACTIVE_STATUSES, STATUSES as PURCHASE_STATUSES

    total_assets             = Asset.objects.count()
    open_tasks_count         = Task.objects(status__ne='done').count()
    pending_allocations_count= Estimate.objects(Q(status='pending') & Q(record_type__ne='estimate')).count()
    open_purchases_count     = Purchase.objects(status__in=ACTIVE_STATUSES).count()

    status_counts = {r['_id']: r['count']
                     for r in Asset._get_collection().aggregate([
                         {'$group': {'_id': '$status', 'count': {'$sum': 1}}}]) if r['_id']}

    dash_commitments = {str(r['_id']): r['total']
                        for r in Estimate._get_collection().aggregate([
                            {'$match': {'status': 'pending', 'record_type': {'$ne': 'estimate'}}},
                            {'$unwind': '$items'},
                            {'$match': {'items.asset': {'$exists': True, '$ne': None}}},
                            {'$group': {'_id': '$items.asset', 'total': {'$sum': '$items.quantity'}}},
                        ])}

    dash_in_purchase = {str(r['_id']): r['total']
                        for r in Purchase._get_collection().aggregate([
                            {'$match': {'status': {'$in': ACTIVE_STATUSES}}},
                            {'$unwind': '$items'},
                            {'$match': {'items.asset': {'$exists': True, '$ne': None}}},
                            {'$group': {'_id': '$items.asset', 'total': {'$sum': '$items.quantity'}}},
                        ])}

    # Low stock — use projection only, store as dicts (picklable)
    low_stock_raw = []
    red_line_count = 0
    for a in Asset.objects(quantity__exists=True, quantity__ne=None).only(
        'id', 'component_id', 'serial_number', 'model', 'quantity', 'min_threshold', 'price_usd'
    ):
        stock     = a.quantity or 0
        committed = dash_commitments.get(str(a.id), 0)
        purchased = dash_in_purchase.get(str(a.id), 0)
        after     = stock + purchased - committed
        threshold = a.min_threshold if (a.min_threshold is not None and a.min_threshold > 0) else None
        if (threshold is not None and after <= threshold) or after < 0:
            red_line_count += 1
            if len(low_stock_raw) < 10:
                low_stock_raw.append(dict(
                    id=str(a.id), component_id=a.component_id, serial_number=a.serial_number,
                    model=a.model, quantity=a.quantity, price_usd=a.price_usd,
                    after=after, threshold=threshold, committed=committed, purchased=purchased,
                ))
    low_stock_raw.sort(key=lambda x: x['after'])

    purchase_status_counts = {r['_id']: r['count']
                              for r in Purchase._get_collection().aggregate([
                                  {'$group': {'_id': '$status', 'count': {'$sum': 1}}}]) if r['_id']}
    purchases_pipeline = [(s, purchase_status_counts.get(s, 0)) for s in PURCHASE_STATUSES]

    _rows = list(Estimate._get_collection().aggregate([
        {'$match': {'status': 'pending', 'record_type': {'$ne': 'estimate'}}},
        {'$unwind': '$items'},
        {'$match': {'items.asset': {'$exists': True, '$ne': None}}},
        {'$group': {'_id': '$items.asset', 'committed': {'$sum': '$items.quantity'}}},
        {'$sort': {'committed': -1}},
        {'$limit': 6},
    ]))
    _asset_ids  = [r['_id'] for r in _rows if r.get('_id')]
    _assets_map = {
        str(a.id): dict(serial_number=a.serial_number, model=a.model,
                        quantity=a.quantity, component_id=a.component_id)
        for a in Asset.objects(id__in=_asset_ids).only('serial_number', 'model', 'quantity', 'component_id')
    }
    top_committed_raw = [
        {'asset': _assets_map[str(r['_id'])], 'committed': r['committed']}
        for r in _rows if r.get('_id') and str(r['_id']) in _assets_map
    ]

    return dict(
        total_assets=total_assets,
        open_tasks_count=open_tasks_count,
        pending_allocations_count=pending_allocations_count,
        open_purchases_count=open_purchases_count,
        status_counts=status_counts,
        low_stock_raw=low_stock_raw,
        red_line_count=red_line_count,
        purchases_pipeline=purchases_pipeline,
        top_committed_raw=top_committed_raw,
    )


@main_bp.route('/')
@login_required
def dashboard():
    if current_user.is_warehouse:
        return redirect(url_for('estimates.list_estimates'))

    from app.models.user import User

    today   = date.today()
    now_utc = datetime.utcnow()

    # ── Heavy data from cache (counts + aggregations) ─────────────────────────
    _d = _dashboard_data()

    # low_stock_assets: wrap dicts in SimpleNamespace so templates use dot notation
    low_stock_assets = [
        types.SimpleNamespace(
            id=x['id'], component_id=x['component_id'], serial_number=x['serial_number'],
            model=x['model'], quantity=x['quantity'], price_usd=x['price_usd'],
            _after=x['after'], _threshold=x['threshold'],
            _committed=x['committed'], _purchased=x['purchased'],
        ) for x in _d['low_stock_raw']
    ]

    # ── Live data ─────────────────────────────────────────────────────────────
    expiring_estimates = _expiring_estimates()

    # user list — cached 15s (no profile_photo — use separate cache)
    _users_raw = cache.get('_dash_users')
    if _users_raw is None:
        _users_raw = list(
            User.objects.only('id', 'name', 'last_seen', 'role', 'last_login')
                        .order_by('-last_seen')
        )
        cache.set('_dash_users', _users_raw, timeout=15)

    all_users = []
    for u in _users_raw:
        if u.last_seen:
            diff     = (now_utc - u.last_seen).total_seconds()
            status   = 'online' if diff < 35 else ('away' if diff < 600 else 'offline')
            diff_min = int(diff / 60)
        else:
            status, diff_min = 'never', None
        all_users.append({'user': u, 'status': status, 'diff_min': diff_min})

    # photos from shared cache (90s TTL) — no extra DB query
    from app.routes.tasks import _user_photos
    user_photos = _user_photos()

    # ── Charts ────────────────────────────────────────────────────────────────
    sc = _d['status_counts']
    all_statuses = ['in_use', 'in_storage', 'assigned', 'faulty']
    status_chart = json.dumps({
        'labels': [_STATUS_LABELS[s] for s in all_statuses],
        'data':   [sc.get(s, 0) for s in all_statuses],
        'colors': [_STATUS_COLORS[s] for s in all_statuses],
    })

    return render_template('dashboard.html',
        total_assets=_d['total_assets'],
        status_counts=sc,
        open_tasks_count=_d['open_tasks_count'],
        pending_allocations_count=_d['pending_allocations_count'],
        open_purchases_count=_d['open_purchases_count'],
        low_stock_assets=low_stock_assets,
        red_line_count=_d['red_line_count'],
        purchases_pipeline=_d['purchases_pipeline'],
        top_committed=_d['top_committed_raw'],
        expiring_estimates=expiring_estimates,
        all_users=all_users,
        user_photos=user_photos,
        now_utc=now_utc,
        today=today,
        status_chart=status_chart,
    )
