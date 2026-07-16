import json
from datetime import date, timedelta, datetime
from urllib.parse import urlparse

from flask import Blueprint, render_template, jsonify, redirect, request, session, url_for, send_from_directory
import os as _os
from flask_login import login_required, current_user
from app.utils.cache import cache

from app.models.asset import Asset, AssetEvent, AssetType
from app.models.task import Task
from app.models.activity import ActivityLog

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
    return jsonify({'ok': True})


@main_bp.route('/api/unread-count')
@login_required
def unread_count():
    me_id = str(current_user.id)
    _ck   = f'unread_{me_id}'
    _hit  = cache.get(_ck)
    if _hit is not None:
        return jsonify({'count': _hit})

    from app.models.chat_message import ChatMessage
    dm_count = ChatMessage.objects(receiver_id=me_id, read=False).count()

    group_count = 0
    try:
        from app.models.chat_last_read import ChatLastRead
        from app.models.chat_group import ChatGroup
        my_groups = list(ChatGroup.objects(member_ids=me_id).only('id'))
        grp_keys  = ['grp_' + str(g.id) for g in my_groups] + ['group']
        last_read_docs = {
            d.room: d.last_read_at
            for d in ChatLastRead.objects(user_id=me_id, room__in=grp_keys)
        }
        if last_read_docs:
            or_conds = [
                {'room': rk, 'timestamp': {'$gt': lr}}
                for rk, lr in last_read_docs.items()
            ]
            for doc in ChatMessage._get_collection().aggregate([
                {'$match': {'$or': or_conds, 'user_id': {'$ne': me_id}, 'deleted': {'$ne': True}}},
                {'$group': {'_id': '$room', 'count': {'$sum': 1}}},
            ]):
                group_count += doc['count']
    except Exception:
        pass

    total = dm_count + group_count
    cache.set(_ck, total, timeout=25)
    return jsonify({'count': total})


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
            if diff < 15:
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
    from app.models.purchase import ACTIVE_STATUSES
    total_assets = Asset.objects.count()
    open_tasks_count = Task.objects(status__ne='done').count()
    pending_allocations_count = Estimate.objects(
        Q(status='pending') & Q(record_type__ne='estimate')
    ).count()
    open_purchases_count = Purchase.objects(
        status__in=ACTIVE_STATUSES
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

    # ── Commitments + in-purchase (same logic as assets list) ────────────────
    _commit_pipeline = [
        {'$match': {'status': 'pending', 'record_type': {'$ne': 'estimate'}}},
        {'$unwind': '$items'},
        {'$match': {'items.asset': {'$exists': True, '$ne': None}}},
        {'$group': {'_id': '$items.asset', 'total': {'$sum': '$items.quantity'}}},
    ]
    dash_commitments = {str(r['_id']): r['total']
                        for r in Estimate._get_collection().aggregate(_commit_pipeline)}

    _purchase_pipeline = [
        {'$match': {'status': {'$in': ACTIVE_STATUSES}}},
        {'$unwind': '$items'},
        {'$match': {'items.asset': {'$exists': True, '$ne': None}}},
        {'$group': {'_id': '$items.asset', 'total': {'$sum': '$items.quantity'}}},
    ]
    dash_in_purchase = {str(r['_id']): r['total']
                        for r in Purchase._get_collection().aggregate(_purchase_pipeline)}

    # ── Low stock — after commitments, only assets with min_threshold set ─────
    low_stock_assets = []
    red_line_count   = 0
    for a in Asset.objects(quantity__exists=True, quantity__ne=None).only(
        'component_id', 'serial_number', 'model', 'quantity', 'min_threshold', 'price_usd'
    ):
        stock     = a.quantity or 0
        committed = dash_commitments.get(str(a.id), 0)
        purchased = dash_in_purchase.get(str(a.id), 0)
        after     = stock + purchased - committed
        threshold = a.min_threshold if (a.min_threshold is not None and a.min_threshold > 0) else None

        is_low = threshold is not None and after <= threshold
        is_neg = after < 0

        if is_low or is_neg:
            red_line_count += 1
            if len(low_stock_assets) < 10:
                a._after     = after
                a._threshold = threshold
                a._committed = committed
                a._purchased = purchased
                low_stock_assets.append(a)

    low_stock_assets.sort(key=lambda a: a._after)

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
    # Batch fetch all assets in one query instead of N individual queries
    _rows       = list(Estimate._get_collection().aggregate(_commit_pipeline))
    _asset_ids  = [r['_id'] for r in _rows if r.get('_id')]
    _assets_map = {
        a.id: a for a in Asset.objects(id__in=_asset_ids).only(
            'serial_number', 'model', 'quantity', 'component_id'
        )
    }
    top_committed = [
        {'asset': _assets_map[r['_id']], 'committed': r['committed']}
        for r in _rows
        if r.get('_id') and r['_id'] in _assets_map
    ]

    # ── Users activity ───────────────────────────────────────────────────────
    now_utc = datetime.utcnow()
    all_users = []
    for u in User.objects.only('id', 'name', 'last_seen', 'role', 'last_login').order_by('-last_seen'):
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
    all_statuses = ['in_use', 'in_storage', 'assigned', 'faulty']
    status_chart = {
        'labels': [_STATUS_LABELS[s] for s in all_statuses],
        'data':   [status_counts.get(s, 0) for s in all_statuses],
        'colors': [_STATUS_COLORS[s] for s in all_statuses],
    }

    # ── Activity feed (last 50 across all modules) ────────────────────────────
    activity_feed = list(ActivityLog.objects.order_by('-created_at').limit(50))

    _ctx = dict(
        total_assets=total_assets,
        status_counts=status_counts,
        recent_events=recent_events,
        open_tasks_count=open_tasks_count,
        pending_allocations_count=pending_allocations_count,
        open_purchases_count=open_purchases_count,
        low_stock_assets=low_stock_assets,
        red_line_count=red_line_count,
        expiring_estimates=expiring_estimates,
        purchases_pipeline=purchases_pipeline,
        top_committed=top_committed,
        all_users=all_users,
        now_utc=now_utc,
        today=today,
        status_chart=json.dumps(status_chart),
        activity_feed=activity_feed,
    )
    return render_template('dashboard.html', **_ctx)
