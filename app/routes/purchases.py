import os
import traceback
from bson import ObjectId
from datetime import datetime
from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, abort, g, current_app)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app.models.purchase import Purchase, PurchaseItem, STATUSES, ACTIVE_STATUSES, MANUAL_STATUSES, CURRENCIES
from app.models.asset import Asset
from app.utils.mongo_helpers import get_or_404

purchases_bp = Blueprint('purchases', __name__, url_prefix='/purchases')


def _sync_inventory_on_cancel(purchase):
    """Subtract received quantities from asset stock when cancelling/reversing an order."""
    col = Asset._get_collection()
    updated = 0
    for item in purchase.items:
        if not item.asset:
            continue
        # Use received_qty if tracked (partial delivery), else fall back to quantity
        qty = item.received_qty or item.quantity or 0
        if qty <= 0:
            continue
        try:
            asset_id = item.asset.id
        except Exception:
            continue
        result = col.update_one(
            {'_id': asset_id},
            [{'$set': {'quantity': {'$max': [0, {'$subtract': [{'$ifNull': ['$quantity', 0]}, qty]}]}}}]
        )
        if result.modified_count:
            updated += 1
    return updated


def _sync_inventory_on_receipt(purchase):
    """Add received quantities to asset stock using atomic $inc. Returns count of updated items."""
    col = Asset._get_collection()
    updated = 0
    for item in purchase.items:
        if not item.asset:
            continue
        qty = item.quantity or 0
        if qty <= 0:
            continue
        try:
            asset_id = item.asset.id
        except Exception:
            continue
        # Pipeline update handles null quantity gracefully
        result = col.update_one(
            {'_id': asset_id},
            [{'$set': {'quantity': {'$add': [{'$ifNull': ['$quantity', 0]}, qty]}}}]
        )
        if result.modified_count:
            updated += 1
    return updated

def _sync_inventory_delta(delta_map):
    """Increment asset stock by delta quantities. delta_map: {asset_id_str: delta_int}"""
    col = Asset._get_collection()
    updated = 0
    for asset_id_str, delta in delta_map.items():
        if delta <= 0:
            continue
        try:
            result = col.update_one(
                {'_id': ObjectId(asset_id_str)},
                [{'$set': {'quantity': {'$add': [{'$ifNull': ['$quantity', 0]}, delta]}}}]
            )
            if result.modified_count:
                updated += 1
        except Exception:
            continue
    return updated


ALLOWED_EXTENSIONS = {'pdf', 'xlsx', 'xls', 'csv', 'doc', 'docx', 'png', 'jpg'}


def _allowed(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _save_bom_file(file):
    if not file or not file.filename:
        return None
    if not _allowed(file.filename):
        return None
    upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'bom')
    os.makedirs(upload_dir, exist_ok=True)
    filename = secure_filename(file.filename)
    ts = datetime.utcnow().strftime('%Y%m%d%H%M%S_')
    filename = ts + filename
    file.save(os.path.join(upload_dir, filename))
    return filename


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
    assets = list(Asset.objects.order_by('component_id').select_related(max_depth=1))
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
    try:
        purchases = list(Purchase.objects.order_by('-created_at'))
    except Exception:
        err = traceback.format_exc()
        current_app.logger.error('list_purchases error:\n' + err)
        flash('שגיאה בטעינת רכשים: ' + err.splitlines()[-1], 'danger')
        purchases = []
    return render_template('purchases/list.html', purchases=purchases)


@purchases_bp.route('/history')
@login_required
def purchase_history():
    try:
        purchases = list(Purchase.objects(status__in=_HISTORY_STATUSES).order_by('-created_at'))
    except Exception:
        err = traceback.format_exc()
        current_app.logger.error('purchase_history error:\n' + err)
        flash('שגיאה בטעינת היסטוריה: ' + err.splitlines()[-1], 'danger')
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
        flash('Error loading assets: ' + err.splitlines()[-1], 'danger')
        return redirect(url_for('purchases.list_purchases'))

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
            flash(t.get('flash_purchase_created', 'Purchase created successfully.'), 'success')
            return redirect(url_for('purchases.list_purchases'))

        except Exception:
            err = traceback.format_exc()
            current_app.logger.error('Purchase create error:\n' + err)
            flash('שגיאה ביצירת רכש: ' + err.splitlines()[-1], 'danger')

    return render_template('purchases/form.html', purchase=None,
                           assets=assets, grouped_assets=grouped_assets,
                           statuses=[s for s in STATUSES if s != 'בוטל'],
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
        flash('Error loading assets: ' + err.splitlines()[-1], 'danger')
        return redirect(url_for('purchases.detail', id=id))
    assets_by_id = {str(a.id): a for a in assets}

    if request.method == 'POST':
        new_file = request.files.get('bom_file')
        bom_filename = purchase.bom_file
        if new_file and new_file.filename:
            saved = _save_bom_file(new_file)
            if saved:
                bom_filename = saved

        old_status = purchase.status
        status = request.form.get('status', purchase.status)
        if status not in STATUSES:
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
        except Exception as e:
            flash(f'Error saving purchase: {e}', 'danger')
            return render_template('purchases/form.html', purchase=purchase,
                                   assets=assets, grouped_assets=grouped_assets,
                                   statuses=MANUAL_STATUSES, currencies=CURRENCIES)

        # ── Inventory sync on status transitions ─────────────────────────────
        _RECEIVED  = 'Order Received in Warehouse'
        _CANCELLED = 'בוטל'

        if old_status != _RECEIVED and status == _RECEIVED:
            # Mark all items as fully received so cancel logic uses received_qty correctly
            for item in purchase.items:
                if item.safe_asset:
                    item.received_qty = item.quantity or 0
            purchase.save()
            # Atomic guard: only the first request to set received_at runs the sync
            guard = Purchase._get_collection().find_one_and_update(
                {'_id': purchase.id, 'received_at': None},
                {'$set': {'received_at': datetime.utcnow()}},
            )
            if guard is not None:
                # We claimed the slot — run sync
                updated = _sync_inventory_on_receipt(purchase)
                if updated > 0:
                    flash(f'{updated} פריטים נוספו למלאי אוטומטית.', 'success')
            # else: another concurrent save already ran the sync — skip silently

        elif old_status == _RECEIVED and status in ACTIVE_STATUSES:
            # Reversed from received → subtract back, clear the guard
            Purchase._get_collection().update_one(
                {'_id': purchase.id},
                {'$unset': {'received_at': ''}}
            )
            updated = _sync_inventory_on_cancel(purchase)
            flash(
                f'הסטטוס שונה בחזרה — {updated} פריטים הופחתו מהמלאי (ביטול קליטה בטעות).',
                'warning'
            )

        elif old_status == _CANCELLED and status in ACTIVE_STATUSES:
            # Reactivated from cancelled → aggregation restores in_purchase automatically
            flash('ההזמנה הופעלה מחדש — הכמויות חזרו לעמודת ברכש אוטומטית.', 'info')

        elif old_status != _CANCELLED and status == _CANCELLED:
            if old_status == _RECEIVED:
                Purchase._get_collection().update_one(
                    {'_id': purchase.id},
                    {'$unset': {'received_at': ''}}
                )
                updated = _sync_inventory_on_cancel(purchase)
                flash(f'ההזמנה בוטלה — {updated} פריטים הופחתו מהמלאי.', 'warning')
            else:
                flash('ההזמנה בוטלה — הכמויות הוסרו מעמודת ברכש אוטומטית.', 'warning')

        flash(t.get('flash_purchase_updated', 'Purchase updated successfully.'), 'success')
        return redirect(url_for('purchases.detail', id=purchase.id))

    return render_template('purchases/form.html', purchase=purchase,
                           assets=assets, grouped_assets=grouped_assets,
                           statuses=MANUAL_STATUSES, currencies=CURRENCIES,
                           ACTIVE_STATUSES=ACTIVE_STATUSES)


@purchases_bp.route('/<id>/delete', methods=['POST'])
@login_required
def delete(id):
    if not current_user.is_admin:
        abort(403)
    t = getattr(g, 't', {})
    purchase = get_or_404(Purchase, id)
    was_received = purchase.status == 'Order Received in Warehouse'
    was_history  = purchase.status in _HISTORY_STATUSES

    if was_received:
        # Quantities were added to inventory when received — subtract them back
        updated = _sync_inventory_on_cancel(purchase)
        purchase.delete()
        flash(
            f'הרכש נמחק — {updated} פריטים הופחתו מהמלאי אוטומטית.',
            'warning'
        )
    else:
        purchase.delete()
        flash(t.get('flash_purchase_deleted', 'Purchase deleted.'), 'warning')

    # Route back to history if the purchase was in the history list
    if was_history:
        return redirect(url_for('purchases.purchase_history'))
    return redirect(url_for('purchases.list_purchases'))


@purchases_bp.route('/<id>/receive', methods=['GET', 'POST'])
@login_required
def receive(id):
    if not current_user.can_edit:
        abort(403)
    purchase = get_or_404(Purchase, id)

    if purchase.status not in ('Order Signed', 'Partial Delivery'):
        flash('קליטת פריטים אפשרית רק לאחר חתימת ההזמנה.', 'warning')
        return redirect(url_for('purchases.edit', id=id))

    if request.method == 'GET':
        return render_template('purchases/receive.html', purchase=purchase)

    # POST — process received quantities
    delta_map = {}
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
            delta_map[asset_id_str] = now_val
            item.received_qty = (item.received_qty or 0) + now_val
            any_received = True

    if delta_map:
        _sync_inventory_delta(delta_map)

    # Recalculate status
    active_items = [i for i in purchase.items if i.safe_asset]
    total        = len(active_items)
    fully_done   = sum(1 for i in active_items if i.is_fully_received)
    any_received_total = sum(1 for i in active_items if (i.received_qty or 0) > 0)

    if fully_done == total and total > 0:
        purchase.status = 'Order Received in Warehouse'
        if not purchase.received_at:
            purchase.received_at = datetime.utcnow()
        flash('כל הפריטים נקלטו — ההזמנה הושלמה!', 'success')
    elif any_received_total > 0:
        purchase.status = 'Partial Delivery'
        received_units = sum(i.received_qty or 0 for i in active_items)
        total_units    = sum(i.quantity or 0 for i in active_items)
        flash(f'קליטה עודכנה — {received_units} מתוך {total_units} יח\' נקלטו.', 'info')
    elif not any_received:
        flash('לא הוזנו כמויות לקליטה.', 'warning')

    purchase.save()
    return redirect(url_for('purchases.receive', id=id))
