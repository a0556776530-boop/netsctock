import os
from datetime import datetime
from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, abort, g, current_app)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app.models.purchase import Purchase, PurchaseItem, STATUSES, CURRENCIES
from app.models.asset import Asset
from app.utils.mongo_helpers import get_or_404

purchases_bp = Blueprint('purchases', __name__, url_prefix='/purchases')

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


@purchases_bp.route('/')
@login_required
def list_purchases():
    purchases = list(Purchase.objects.order_by('-created_at'))
    return render_template('purchases/list.html', purchases=purchases, statuses=STATUSES)


@purchases_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_purchase():
    if not current_user.can_edit:
        abort(403)
    t = getattr(g, 't', {})
    assets = list(Asset.objects.order_by('component_id'))
    assets_by_id = {str(a.id): a for a in assets}

    if request.method == 'POST':
        bom_filename = _save_bom_file(request.files.get('bom_file'))
        status = request.form.get('status', 'BOM Transferred')
        if status not in STATUSES:
            status = 'BOM Transferred'
        currency = request.form.get('currency', 'ILS')
        if currency not in CURRENCIES:
            currency = 'ILS'

        name = request.form.get('name', '').strip()
        if not name:
            flash(t.get('flash_name_required', 'Purchase name is required.'), 'danger')
            return render_template('purchases/form.html', purchase=None,
                                   assets=assets, statuses=STATUSES, currencies=CURRENCIES)

        p = Purchase(
            name            = name,
            bom_date        = _parse_date(request.form.get('bom_date')),
            estimate_number = request.form.get('estimate_number', '').strip() or None,
            amount          = _parse_amount(request.form.get('amount')),
            currency        = currency,
            emf             = request.form.get('emf', '').strip() or None,
            requirement     = request.form.get('requirement', '').strip() or None,
            order           = request.form.get('order', '').strip() or None,
            status          = status,
            bom_file        = bom_filename,
            items           = _parse_items(request.form, assets_by_id),
        )
        p.save()
        flash(t.get('flash_purchase_created', 'Purchase created successfully.'), 'success')
        return redirect(url_for('purchases.list_purchases'))

    return render_template('purchases/form.html', purchase=None,
                           assets=assets, statuses=STATUSES, currencies=CURRENCIES)


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
    assets = list(Asset.objects.order_by('component_id'))
    assets_by_id = {str(a.id): a for a in assets}

    if request.method == 'POST':
        new_file = request.files.get('bom_file')
        bom_filename = purchase.bom_file
        if new_file and new_file.filename:
            saved = _save_bom_file(new_file)
            if saved:
                bom_filename = saved

        status = request.form.get('status', purchase.status)
        if status not in STATUSES:
            status = purchase.status
        currency = request.form.get('currency', purchase.currency)
        if currency not in CURRENCIES:
            currency = purchase.currency

        name = request.form.get('name', '').strip() or purchase.name
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
        purchase.save()
        flash(t.get('flash_purchase_updated', 'Purchase updated successfully.'), 'success')
        return redirect(url_for('purchases.detail', id=purchase.id))

    return render_template('purchases/form.html', purchase=purchase,
                           assets=assets, statuses=STATUSES, currencies=CURRENCIES)


@purchases_bp.route('/<id>/delete', methods=['POST'])
@login_required
def delete(id):
    if not current_user.is_admin:
        abort(403)
    purchase = get_or_404(Purchase, id)
    purchase.delete()
    t = getattr(g, 't', {})
    flash(t.get('flash_purchase_deleted', 'Purchase deleted.'), 'warning')
    return redirect(url_for('purchases.list_purchases'))
