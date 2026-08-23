import os
import traceback
from datetime import datetime
from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, abort, g, current_app, jsonify, send_from_directory)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import cache

from app.models.purchase import Purchase, PurchaseItem, STATUSES, ACTIVE_STATUSES, MANUAL_STATUSES, CURRENCIES, STATUS_COLORS
from app.models.asset import Asset
from app.utils.mongo_helpers import get_or_404
from app.utils.activity import log_activity

purchases_bp = Blueprint('purchases', __name__, url_prefix='/purchases')




ALLOWED_EXTENSIONS = {'pdf', 'xlsx', 'xls', 'csv', 'doc', 'docx', 'png', 'jpg'}


def _invalidate_purchases_cache():
    cache.delete('purchases_active')
    cache.delete('purchases_history')


def _allowed(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _bom_dir():
    d = os.path.join(current_app.root_path, 'uploads', 'bom')
    os.makedirs(d, exist_ok=True)
    return d


def _save_bom_file(file):
    if not file or not file.filename:
        return None
    if not _allowed(file.filename):
        return None
    filename = secure_filename(file.filename)
    ts = datetime.utcnow().strftime('%Y%m%d%H%M%S_')
    filename = ts + filename
    file.save(os.path.join(_bom_dir(), filename))
    return filename


@purchases_bp.route('/bom/<path:filename>')
@login_required
def serve_bom(filename):
    return send_from_directory(_bom_dir(), filename)


def _parse_date(val):
    if not val:
        return None
    try:
        return datetime.strptime(val.strip(), '%Y-%m-%d')
    except ValueError:
        return None


def _parse_items(form, assets_by_id):
    items = []
    ids  = form.getlist('item_asset_id')
    qtys = form.getlist('item_quantity')
    for aid, qty in zip(ids, qtys):
        if not aid or not qty:
            continue
        asset = assets_by_id.get(aid)
        if not asset:
            continue
        try:
            q = int(qty)
        except ValueError:
            continue
        if q < 1:
            continue
        items.append(PurchaseItem(asset=asset, quantity=q))
    return items


def _parse_amount(val):
    if not val:
        return None
    try:
        return float(str(val).replace(',', ''))
    except ValueError:
        return None


def _grouped_assets():
    from collections import defaultdict
    # select_related eagerly loads asset_type — prevents N lazy-load queries in the loop
    assets = list(Asset.objects.only(
        'id', 'component_id', 'serial_number', 'model', 'asset_type', 'price_usd', 'price_nis'
    ).order_by('component_id').select_related(max_depth=1))
    groups = defaultdict(list)
    for a in assets:
        try:
            cat = a.asset_type.name if a.asset_type else '—'
        except Exception:
            cat = '—'
        groups[cat].append(a)
    return assets, sorted(groups.items())


_HISTORY_STATUSES = ['Order Received in Warehouse', 'בוטל']


@purchases_bp.route('/')
@login_required
def list_purchases():
    if current_user.is_warehouse:
        abort(403)
    try:
        purchases = cache.get('purchases_active')
        if purchases is None:
            purchases = list(Purchase.objects.order_by('-created_at'))
            cache.set('purchases_active', purchases, timeout=30)
    except Exception:
        err = traceback.format_exc()
        current_app.logger.error('list_purchases error:\n' + err)
        flash('שגיאה בטעינת רכשים. נסה שוב.', 'danger')
        purchases = []
    return render_template('purchases/list.html', purchases=purchases, manual_statuses=MANUAL_STATUSES)


@purchases_bp.route('/history')
@login_required
def purchase_history():
    if current_user.is_warehouse:
        abort(403)
    try:
        purchases = cache.get('purchases_history')
        if purchases is None:
            purchases = list(Purchase.objects(status__in=_HISTORY_STATUSES).order_by('-created_at'))
            cache.set('purchases_history', purchases, timeout=30)
    except Exception:
        err = traceback.format_exc()
        current_app.logger.error('purchase_history error:\n' + err)
        flash('שגיאה בטעינת היסטוריה. נסה שוב.', 'danger')
        purchases = []
    return render_template('purchases/history.html', purchases=purchases)


@purchases_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_purchase():
    if not current_user.can_edit:
        abort(403)
    t = getattr(g, 't', {})

    try:
        assets, grouped_assets = _grouped_assets()
    except Exception:
        err = traceback.format_exc()
        current_app.logger.error('new_purchase _grouped_assets error:\n' + err)
        flash('Error loading data. Please try again.', 'danger')
        return redirect(url_for('purchases.list_purchases') + '?status=all')

    assets_by_id = {str(a.id): a for a in assets}

    if request.method == 'POST':
        try:
            bom_filename = None
            f = request.files.get('bom_file')
            if f and f.filename:
                bom_filename = _save_bom_file(f)

            status = request.form.get('status', 'BOM Transferred')
            if status not in STATUSES:
                status = 'BOM Transferred'
            currency = request.form.get('currency', 'ILS')
            if currency not in CURRENCIES:
                currency = 'ILS'

            name = request.form.get('name', '').strip()
            if not name:
                flash(t.get('flash_name_required', 'Purchase name is required.'), 'danger')
                # Build prefill_items so the items list is preserved
                asset_ids = request.form.getlist('item_asset_id')
                quantities = request.form.getlist('item_quantity')
                prefill_items = []
                for aid, qty in zip(asset_ids, quantities):
                    a = assets_by_id.get(aid)
                    if a:
                        prefill_items.append({'asset': a, 'quantity': int(qty or 1)})
                return render_template('purchases/form.html', purchase=None,
                                       assets=assets, grouped_assets=grouped_assets,
                                       statuses=MANUAL_STATUSES, currencies=CURRENCIES,
                                       form_data=request.form,
                                       prefill_items=prefill_items)

            bom_date = _parse_date(request.form.get('bom_date'))
            estimate_number = request.form.get('estimate_number', '').strip() or None
            amount = _parse_amount(request.form.get('amount'))
            emf = request.form.get('emf', '').strip() or None
            requirement = request.form.get('requirement', '').strip() or None
            order = request.form.get('order', '').strip() or None
            items = _parse_items(request.form, assets_by_id)

            p = Purchase(
                name            = name,
                bom_date        = bom_date,
                estimate_number = estimate_number,
                amount          = amount,
                currency        = currency,
                emf             = emf,
                requirement     = requirement,
                order           = order,
                status          = status,
                bom_file        = bom_filename,
                items           = items,
            )
            p.save()
            _invalidate_purchases_cache()
            log_activity(current_user, 'purchase_created', f'יצר רכש חדש: {name}')
            flash(t.get('flash_purchase_created', 'Purchase created successfully.'), 'success')
            return redirect(url_for('purchases.list_purchases') + '?status=all')

        except Exception:
            err = traceback.format_exc()
            current_app.logger.error('Purchase create error:\n' + err)
            flash('שגיאה ביצירת רכש. נסה שוב.', 'danger')

    return render_template('purchases/form.html', purchase=None,
                           assets=assets, grouped_assets=grouped_assets,
                           statuses=[s for s in MANUAL_STATUSES if s != 'בוטל'],
                           currencies=CURRENCIES,
                           form_data=None, prefill_items=[])


@purchases_bp.route('/<id>')
@login_required
def detail(id):
    purchase = get_or_404(Purchase, id)
    return render_template('purchases/detail.html', purchase=purchase)


@purchases_bp.route('/<id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    if not current_user.can_edit:
        abort(403)
    t = getattr(g, 't', {})
    purchase = get_or_404(Purchase, id)
    try:
        assets, grouped_assets = _grouped_assets()
    except Exception:
        err = traceback.format_exc()
        current_app.logger.error('edit _grouped_assets error:\n' + err)
        flash('Error loading data. Please try again.', 'danger')
        return redirect(url_for('purchases.detail', id=id))
    assets_by_id = {str(a.id): a for a in assets}

    if purchase.status in ('Order Received in Warehouse', 'בוטל'):
        flash(t.get('flash_purchase_edit_locked', 'Cannot edit an order in this status.'), 'warning')
        return redirect(url_for('purchases.detail', id=purchase.id))

    if request.method == 'POST':
        new_file = request.files.get('bom_file')
        bom_filename = purchase.bom_file
        if new_file and new_file.filename:
            saved = _save_bom_file(new_file)
            if saved:
                bom_filename = saved

        old_status = purchase.status
        if old_status in ('Order Received in Warehouse', 'בוטל'):
            flash(t.get('flash_purchase_edit_locked', 'Cannot edit an order in this status.'), 'warning')
            return redirect(url_for('purchases.detail', id=purchase.id))
        status = request.form.get('status', purchase.status)
        if status not in STATUSES:
            status = purchase.status
        # Cannot set TO "Order Received in Warehouse" from edit form — warehouse page only
        if status == 'Order Received in Warehouse':
            status = purchase.status
        currency = request.form.get('currency', purchase.currency)
        if currency not in CURRENCIES:
            currency = purchase.currency

        name = request.form.get('name', '').strip()
        if not name:
            flash(t.get('flash_name_required', 'Task name is required.'), 'danger')
            return redirect(url_for('purchases.edit', id=purchase.id))
        purchase.name            = name
        purchase.bom_date        = _parse_date(request.form.get('bom_date'))
        purchase.estimate_number = request.form.get('estimate_number', '').strip() or None
        purchase.amount          = _parse_amount(request.form.get('amount'))
        purchase.currency        = currency
        purchase.emf             = request.form.get('emf', '').strip() or None
        purchase.requirement     = request.form.get('requirement', '').strip() or None
        purchase.order           = request.form.get('order', '').strip() or None
        purchase.status          = status
        purchase.bom_file        = bom_filename
        purchase.items           = _parse_items(request.form, assets_by_id)
        try:
            purchase.save()
            _invalidate_purchases_cache()
        except Exception as e:
            flash(f'Error saving purchase: {e}', 'danger')
            return render_template('purchases/form.html', purchase=purchase,
                                   assets=assets, grouped_assets=grouped_assets,
                                   statuses=MANUAL_STATUSES, currencies=CURRENCIES)

        _RECEIVED  = 'Order Received in Warehouse'
        _CANCELLED = 'בוטל'

        if old_status == _RECEIVED and status in ACTIVE_STATUSES:
            Purchase._get_collection().update_one(
                {'_id': purchase.id},
                {'$unset': {'received_at': ''}}
            )
            flash('הסטטוס שונה בחזרה — הקליטה בוטלה.', 'warning')

        elif old_status == _CANCELLED and status in ACTIVE_STATUSES:
            flash('ההזמנה הופעלה מחדש.', 'info')

        elif old_status != _CANCELLED and status == _CANCELLED:
            if old_status == _RECEIVED:
                Purchase._get_collection().update_one(
                    {'_id': purchase.id},
                    {'$unset': {'received_at': ''}}
                )
            flash('ההזמנה בוטלה.', 'warning')

        log_activity(current_user, 'purchase_updated', f'עדכן רכש: {purchase.name}')
        flash(t.get('flash_purchase_updated', 'Purchase updated successfully.'), 'success')
        return redirect(url_for('purchases.detail', id=purchase.id))

    return render_template('purchases/form.html', purchase=purchase,
                           assets=assets, grouped_assets=grouped_assets,
                           statuses=MANUAL_STATUSES, currencies=CURRENCIES,
                           ACTIVE_STATUSES=ACTIVE_STATUSES)


@purchases_bp.route('/<id>/quick-status', methods=['POST'])
@login_required
def quick_status(id):
    if not current_user.can_edit:
        return jsonify({'ok': False, 'error': 'אין הרשאה'}), 403
    purchase = get_or_404(Purchase, id)
    new_status = request.form.get('status', '').strip()
    if new_status not in MANUAL_STATUSES:
        return jsonify({'ok': False, 'error': 'סטטוס לא חוקי'}), 400

    old_status = purchase.status
    _RECEIVED  = 'Order Received in Warehouse'
    _CANCELLED = 'בוטל'
    t = getattr(g, 't', {})

    # "Order Received in Warehouse" is a warehouse-only terminal status — admin cannot
    # change FROM it either. Use delete or a dedicated admin action to correct mistakes.
    if old_status == _RECEIVED:
        return jsonify({'ok': False, 'error': t.get('flash_purchase_status_locked', 'Cannot change the status of a received order.')}), 400

    purchase.status = new_status

    if old_status == _RECEIVED and new_status in ACTIVE_STATUSES:
        Purchase._get_collection().update_one(
            {'_id': purchase.id}, {'$unset': {'received_at': ''}}
        )

    elif old_status != _CANCELLED and new_status == _CANCELLED:
        if old_status == _RECEIVED:
            Purchase._get_collection().update_one(
                {'_id': purchase.id}, {'$unset': {'received_at': ''}}
            )

    purchase.save()
    _invalidate_purchases_cache()
    log_activity(current_user, 'purchase_status', f'עדכן סטטוס רכש: {purchase.name} → {new_status}')

    key = 'purchase_status_' + new_status.lower().replace(' ', '_')
    label = t.get(key, new_status)
    return jsonify({'ok': True, 'status': new_status, 'color': STATUS_COLORS.get(new_status, 'secondary'), 'label': label})


@purchases_bp.route('/<id>/delete', methods=['POST'])
@login_required
def delete(id):
    if not current_user.is_admin:
        abort(403)
    t = getattr(g, 't', {})
    purchase = get_or_404(Purchase, id)
    was_received = purchase.status == 'Order Received in Warehouse'
    was_history  = purchase.status in _HISTORY_STATUSES

    purchase.delete()
    _invalidate_purchases_cache()
    flash(t.get('flash_purchase_deleted', 'Purchase deleted.'), 'warning')

    # Route back to history if the purchase was in the history list
    if was_history:
        return redirect(url_for('purchases.purchase_history'))
    return redirect(url_for('purchases.list_purchases') + '?status=all')


@purchases_bp.route('/<id>/items-json')
@login_required
def items_json(id):
    if not current_user.can_edit:
        return jsonify({'ok': False, 'error': 'אין הרשאה'}), 403
    purchase = get_or_404(Purchase, id)
    items = []
    for item in purchase.items:
        a = item.safe_asset
        if not a:
            continue
        items.append({
            'asset_id':        str(a.id),
            'serial_number':   a.serial_number or '',
            'model':           a.model or '',
            'quantity':        item.quantity or 0,
            'received_qty':    item.received_qty or 0,
            'is_fully_received': item.is_fully_received,
        })
    return jsonify({'ok': True, 'name': purchase.name, 'items': items})


@purchases_bp.route('/<id>/verify', methods=['POST'])
@login_required
def verify(id):
    if not current_user.can_edit:
        return jsonify({'ok': False, 'error': 'אין הרשאה'}), 403
    t = getattr(g, 't', {})
    purchase = get_or_404(Purchase, id)

    if purchase.status not in ('Order Signed', 'Partial Delivery'):
        return jsonify({'ok': False, 'error': t.get('flash_purchase_receive_early', 'לא ניתן לקלוט בסטטוס זה')}), 400

    verified_ids = set(request.form.getlist('verified_ids[]'))

    for item in purchase.items:
        a = item.safe_asset
        if not a:
            continue
        asset_id_str = str(a.id)
        if asset_id_str in verified_ids and not item.is_fully_received:
            remaining = (item.quantity or 0) - (item.received_qty or 0)
            try:
                qty = int(request.form.get('qty_' + asset_id_str, remaining))
            except (ValueError, TypeError):
                qty = remaining
            qty = max(0, min(qty, remaining))
            if qty > 0:
                item.received_qty = (item.received_qty or 0) + qty

    active_items  = [i for i in purchase.items if i.safe_asset]
    total         = len(active_items)
    fully_done    = sum(1 for i in active_items if i.is_fully_received)
    any_received  = sum(1 for i in active_items if (i.received_qty or 0) > 0)

    if fully_done == total and total > 0:
        purchase.status = 'Order Received in Warehouse'
        if not purchase.received_at:
            purchase.received_at = datetime.utcnow()
    elif any_received > 0:
        purchase.status = 'Partial Delivery'

    purchase.save()
    _invalidate_purchases_cache()

    skey  = 'purchase_status_' + purchase.status.lower().replace(' ', '_')
    label = t.get(skey, purchase.status)
    return jsonify({
        'ok':        True,
        'status':    purchase.status,
        'color':     STATUS_COLORS.get(purchase.status, 'secondary'),
        'label':     label,
        'fully_done': fully_done,
        'total':     total,
    })


@purchases_bp.route('/<id>/receive', methods=['GET', 'POST'])
@login_required
def receive(id):
    if not current_user.can_edit:
        abort(403)
    t = getattr(g, 't', {})
    purchase = get_or_404(Purchase, id)

    if purchase.status not in ('Order Signed', 'Partial Delivery', 'Order Received in Warehouse'):
        flash(t.get('flash_purchase_receive_early', 'Items can only be received after the order is signed.'), 'warning')
        return redirect(url_for('purchases.list_purchases') + '?status=all')

    if request.method == 'GET':
        return render_template('purchases/receive.html', purchase=purchase)

    # POST — process received quantities
    any_received = False
    for item in purchase.items:
        a = item.safe_asset
        if not a:
            continue
        asset_id_str = str(a.id)
        key = f'received_now_{asset_id_str}'
        try:
            now_val = int(request.form.get(key, 0) or 0)
        except (ValueError, TypeError):
            now_val = 0
        now_val = max(0, min(now_val, item.remaining_qty))
        if now_val > 0:
            item.received_qty = (item.received_qty or 0) + now_val
            any_received = True

    # Recalculate status
    active_items = [i for i in purchase.items if i.safe_asset]
    total        = len(active_items)
    fully_done   = sum(1 for i in active_items if i.is_fully_received)
    any_received_total = sum(1 for i in active_items if (i.received_qty or 0) > 0)

    fully_received_now = fully_done == total and total > 0
    if fully_received_now:
        purchase.status = 'Order Received in Warehouse'
        if not purchase.received_at:
            purchase.received_at = datetime.utcnow()
        log_activity(current_user, 'purchase_received', f'קלט לפי הזמנה: {purchase.name}')
        flash(t.get('flash_all_items_received', 'All items received — order completed!'), 'success')
    elif any_received_total > 0:
        purchase.status = 'Partial Delivery'
        received_units = sum(i.received_qty or 0 for i in active_items)
        total_units    = sum(i.quantity or 0 for i in active_items)
        flash(t.get('flash_partial_receipt', 'Receipt updated — {received} of {total} units received.').format(received=received_units, total=total_units), 'info')
    elif not any_received:
        flash(t.get('flash_no_quantities_entered', 'No quantities were entered.'), 'warning')

    purchase.save()
    _invalidate_purchases_cache()
    return redirect(url_for('purchases.list_purchases') + '?status=all')
