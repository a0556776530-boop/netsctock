import csv
import io
import json
from datetime import date, timedelta, datetime, timezone

from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, Response, jsonify, g
from mongoengine import Q
from mongoengine.errors import NotUniqueError
from flask_login import login_required, current_user

from app.models.estimate import Estimate, EstimateItem
from app.models.asset import Asset
from app.models.settings import AppSetting
from app.utils.mongo_helpers import get_or_404

estimates_bp = Blueprint('estimates', __name__, url_prefix='/estimates')


def _next_allocation_number():
    """Return next suggested allocation number based on internal counter.

    Uses 'alloc_counter' in AppSetting — only updated when user accepts
    the auto-suggested number.  Manual overrides (high or low) never
    advance the counter, so the sequence stays coherent.
    On first run, seeds from the current DB max so nothing is lost.
    """
    # Seed from DB max on first use (counter not yet stored)
    counter_row = AppSetting._get_collection().find_one({'_id': 'alloc_counter'})
    if counter_row is None:
        result = list(Estimate._get_collection().aggregate([
            {'$match': {'allocation_number': {'$exists': True, '$ne': None}}},
            {'$group': {'_id': None, 'max_num': {'$max': '$allocation_number'}}},
        ]))
        seed = result[0]['max_num'] if result else 1000
        AppSetting.set('alloc_counter', seed)

    counter = int(AppSetting.get('alloc_counter') or 1000)
    proposed = counter + 1
    # Skip numbers already taken (e.g. manual overrides that landed here)
    while Estimate.objects(allocation_number=proposed).first():
        proposed += 1
    return proposed


@estimates_bp.route('/')
@login_required
def list_estimates():
    # Show allocations (legacy docs without record_type are treated as allocations)
    estimates = list(
        Estimate.objects(
            Q(status='pending') & Q(record_type__ne='estimate') & Q(warehouse_status__ne='completed')
        ).order_by('-created_at')
    )
    return render_template('estimates/list.html', estimates=estimates)


@estimates_bp.route('/budget')
@login_required
def list_budget_estimates():
    if not current_user.is_super_admin:
        abort(403)
    t = getattr(g, 't', {})
    estimates = list(Estimate.objects(record_type='estimate').order_by('-created_at'))
    return render_template('estimates/budget_list.html', estimates=estimates)


@estimates_bp.route('/history')
@login_required
def history():
    estimates = list(Estimate.objects(status='withdrawn').order_by('-created_at'))
    return render_template('estimates/history.html', estimates=estimates)


@estimates_bp.route('/check-allocation')
@login_required
def check_allocation():
    num        = request.args.get('num', type=int)
    exclude_id = request.args.get('exclude', '')
    if not num:
        return jsonify(exists=False)
    qs = Estimate.objects(allocation_number=num)
    conflict = None
    for est in qs:
        if exclude_id and str(est.id) == exclude_id:
            continue
        conflict = est
        break
    if conflict:
        return jsonify(exists=True, task_name=conflict.task_name)
    return jsonify(exists=False)


@estimates_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_estimate():
    if not current_user.can_edit:
        abort(403)
    from app.models.settings import EFFECTIVE_RATE
    usd_rate = EFFECTIVE_RATE  # 3.6 × 1.048 ≈ 3.7728
    today    = date.today()
    validity = today + timedelta(days=90)

    # Always build assets list (needed for both GET and POST re-render)
    assets = list(Asset.objects(price_usd__exists=True, price_usd__ne=None).order_by('serial_number').select_related())
    assets_json = json.dumps([{
        'id':            str(a.id),
        'component_id':  a.component_id or '',
        'serial_number': a.serial_number,
        'model':         a.model or '',
        'manufacturer':  a.manufacturer or '',
        'type':          a.asset_type.name if a.asset_type else '',
        'price_usd':     float(a.price_usd),
        'quantity':      a.quantity if a.quantity is not None else 0,
    } for a in assets])
    maint_factor = float(AppSetting.get('maintenance_factor') or 1.7)

    def _rerender(error_msg, form_data):
        flash(error_msg, 'danger')
        return render_template('estimates/new.html',
                               assets_json=assets_json,
                               usd_rate=float(usd_rate),
                               maint_factor=maint_factor,
                               today=today,
                               valid_until=validity,
                               next_num=form_data.get('next_num', _next_allocation_number()),
                               prefill=form_data)

    if request.method == 'POST':
        task_name    = (request.form.get('task_name') or '').strip()
        project_name = (request.form.get('project_name') or '').strip()
        items_raw    = request.form.get('items_json', '[]')
        alloc_raw    = (request.form.get('allocation_number') or '').strip()
        record_type  = request.form.get('record_type', 'allocation')

        suggested_raw = (request.form.get('alloc_suggested') or '').strip()
        suggested_num = int(suggested_raw) if suggested_raw.isdigit() else None

        _form_data = {
            'task_name':    task_name,
            'project_name': project_name,
            'items_raw':    items_raw,
            'alloc_num':    alloc_raw,
            'record_type':  record_type,
            'next_num':     int(alloc_raw) if alloc_raw.isdigit() and int(alloc_raw) > 0 else _next_allocation_number(),
            'suggested':    suggested_num,
        }

        if not task_name:
            return _rerender('Task name is required.', _form_data)

        try:
            items_data = json.loads(items_raw)
        except (json.JSONDecodeError, TypeError):
            items_data = []

        next_num = _form_data['next_num']

        conflict = Estimate.objects(allocation_number=next_num).first()
        if conflict:
            return _rerender(
                f'Allocation number {next_num} is already in use '
                f'(assigned to "{conflict.task_name}"). Please choose a different number.',
                _form_data,
            )

        if record_type not in ('allocation', 'estimate'):
            record_type = 'allocation'
        estimate = Estimate(
            allocation_number=next_num,
            task_name=task_name,
            project_name=project_name or None,
            created_date=today,
            valid_until=validity,
            usd_rate=usd_rate,
            maintenance_factor=maint_factor,
            record_type=record_type,
            created_by=current_user._get_current_object(),
        )

        total_nis = 0.0
        for item in items_data:
            try:
                asset_id = str(item['asset_id'])
                qty      = max(1, int(item.get('quantity', 1)))
            except (KeyError, ValueError, TypeError):
                continue
            asset = Asset.objects(id=asset_id).first()
            if not asset or not asset.price_usd:
                continue
            unit_usd = float(asset.price_usd)
            line_nis  = round(unit_usd * float(usd_rate) * maint_factor * 1.18 * qty, 2)
            total_nis += line_nis
            estimate.items.append(EstimateItem(asset=asset, quantity=qty, unit_price_usd=unit_usd))

        if not estimate.items:
            return _rerender('לא ניתן לשמור הצעה ללא פריטים. הוסף לפחות פריט אחד.', _form_data)

        estimate.total_nis = round(total_nis, 2)
        try:
            estimate.save()
        except NotUniqueError:
            estimate.allocation_number = _next_allocation_number()
            try:
                estimate.save()
            except NotUniqueError:
                flash('מספר הקצאה נתפס במקביל. נסה שוב.', 'danger')
                return redirect(url_for('estimates.new_estimate'))

        # Advance counter ONLY when user accepted the auto-suggestion.
        # Manual overrides (higher or lower) are saved as-is but never
        # shift the counter — next suggestion stays coherent.
        suggested = _form_data.get('suggested')
        if suggested and next_num == suggested:
            AppSetting.set('alloc_counter', next_num)

        flash(f'Estimate "{task_name}" saved successfully.', 'success')
        if record_type == 'estimate':
            return redirect(url_for('estimates.list_budget_estimates'))
        return redirect(url_for('estimates.list_estimates'))

    # GET
    return render_template('estimates/new.html',
                           assets_json=assets_json,
                           usd_rate=float(usd_rate),
                           maint_factor=maint_factor,
                           today=today,
                           valid_until=validity,
                           next_num=_next_allocation_number(),
                           prefill=None)


@estimates_bp.route('/<id>')
@login_required
def detail(id):
    estimate = get_or_404(Estimate, id)
    rec_type = getattr(estimate, 'record_type', 'allocation') or 'allocation'
    # Budget estimates are super-admin only
    if rec_type == 'estimate' and not current_user.is_super_admin:
        abort(403)
    # Warehouse workers can only view allocations
    if current_user.is_warehouse and rec_type != 'allocation':
        abort(403)
    return render_template('estimates/detail.html', estimate=estimate)


@estimates_bp.route('/<id>/withdraw', methods=['POST'])
@login_required
def withdraw(id):
    if not current_user.can_edit:
        abort(403)
    estimate = get_or_404(Estimate, id)
    if estimate.status != 'pending':
        flash('לא ניתן לבצע פעולה זו — ההקצאה אינה במצב פעיל.', 'warning')
        return redirect(url_for('estimates.detail', id=str(estimate.id)))
    estimate.status       = 'withdrawn'
    israel_tz = timezone(timedelta(hours=3))
    estimate.withdrawn_at = datetime.now(israel_tz).replace(tzinfo=None)
    estimate.save()
    flash(f'Assignment {estimate.allocation_number} marked as ongoing and moved to History.', 'success')
    return redirect(url_for('estimates.detail', id=str(estimate.id)))


@estimates_bp.route('/<id>/restore', methods=['POST'])
@login_required
def restore(id):
    if not current_user.can_edit:
        abort(403)
    estimate = get_or_404(Estimate, id)
    if estimate.status != 'withdrawn':
        flash('לא ניתן לשחזר הקצאה שאינה בארכיון.', 'warning')
        return redirect(url_for('estimates.detail', id=str(estimate.id)))
    estimate.status       = 'pending'
    estimate.withdrawn_at = None
    estimate.save()
    flash(f'Assignment {estimate.allocation_number} restored to Pending.', 'success')
    return redirect(url_for('estimates.detail', id=str(estimate.id)))


@estimates_bp.route('/<id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    if not current_user.can_edit:
        abort(403)
    estimate = get_or_404(Estimate, id)
    usd_rate = float(estimate.usd_rate)

    if request.method == 'POST':
        task_name    = (request.form.get('task_name') or '').strip()
        project_name = (request.form.get('project_name') or '').strip()
        items_raw    = request.form.get('items_json', '[]')

        if not task_name:
            flash('Requester name is required.', 'danger')
            return redirect(url_for('estimates.edit', id=str(estimate.id)))

        try:
            items_data = json.loads(items_raw)
        except (json.JSONDecodeError, TypeError):
            items_data = []

        alloc_raw = (request.form.get('allocation_number') or '').strip()
        if alloc_raw.isdigit() and int(alloc_raw) > 0:
            new_alloc = int(alloc_raw)
            for e in Estimate.objects(allocation_number=new_alloc):
                if str(e.id) != str(estimate.id):
                    flash(
                        f'Allocation number {new_alloc} is already in use '
                        f'(assigned to "{e.task_name}"). Please choose a different number.',
                        'danger',
                    )
                    return redirect(url_for('estimates.edit', id=str(estimate.id)))
            estimate.allocation_number = new_alloc

        maint_factor = float(estimate.maintenance_factor or AppSetting.get('maintenance_factor') or 1.7)
        estimate.task_name    = task_name
        estimate.project_name = project_name or None
        estimate.items        = []

        total_nis = 0.0
        for item in items_data:
            try:
                asset_id = str(item['asset_id'])
                qty      = max(1, int(item.get('quantity', 1)))
            except (KeyError, ValueError, TypeError):
                continue
            asset = Asset.objects(id=asset_id).first()
            if not asset or not asset.price_usd:
                continue
            unit_usd  = float(asset.price_usd)
            line_nis  = round(unit_usd * usd_rate * maint_factor * 1.18 * qty, 2)
            total_nis += line_nis
            estimate.items.append(EstimateItem(asset=asset, quantity=qty, unit_price_usd=unit_usd))

        if not estimate.items:
            flash('לא ניתן לשמור הצעה ללא פריטים. הוסף לפחות פריט אחד.', 'danger')
            return redirect(url_for('estimates.edit', id=str(estimate.id)))

        estimate.total_nis = round(total_nis, 2)
        try:
            estimate.save()
        except NotUniqueError:
            estimate.allocation_number = _next_allocation_number()
            try:
                estimate.save()
            except NotUniqueError:
                flash('מספר הקצאה נתפס במקביל. נסה שוב.', 'danger')
                return redirect(url_for('estimates.edit', id=str(estimate.id)))
        flash('Estimate updated successfully.', 'success')
        return redirect(url_for('estimates.detail', id=str(estimate.id)))

    assets = list(Asset.objects(price_usd__exists=True, price_usd__ne=None).order_by('serial_number').select_related())
    assets_json = json.dumps([{
        'id':            str(a.id),
        'component_id':  a.component_id or '',
        'serial_number': a.serial_number,
        'model':         a.model or '',
        'manufacturer':  a.manufacturer or '',
        'type':          a.asset_type.name if a.asset_type else '',
        'price_usd':     float(a.price_usd),
        'quantity':      a.quantity if a.quantity is not None else 0,
    } for a in assets])

    selected_json = json.dumps([{
        'asset_id': str(item.asset.id) if item.asset else None,
        'quantity': item.quantity,
    } for item in estimate.items])

    stored_factor = float(estimate.maintenance_factor or AppSetting.get('maintenance_factor') or 1.7)
    return render_template('estimates/edit.html',
                           estimate=estimate, assets_json=assets_json,
                           selected_json=selected_json, usd_rate=usd_rate,
                           maint_factor=stored_factor)


@estimates_bp.route('/<id>/export.csv')
@login_required
def export_csv(id):
    estimate = get_or_404(Estimate, id)
    buf = io.StringIO()
    w   = csv.writer(buf)
    w.writerow(['Allocation Number', estimate.allocation_number or ''])
    w.writerow(['Requester Name', estimate.task_name])
    w.writerow(['Project', estimate.project_name or ''])
    w.writerow(['Date',        estimate.created_date.strftime('%d %b %Y') if estimate.created_date else ''])
    w.writerow(['Valid Until', estimate.valid_until.strftime('%d %b %Y') if estimate.valid_until else ''])
    w.writerow([])
    w.writerow(['Part No.','Description','Type','Qty','Unit Price (USD)','Unit Price (ILS)','Line Total (ILS)'])
    rate   = float(estimate.usd_rate)
    factor = float(estimate.maintenance_factor or 1.7)
    for item in estimate.items:
        # Resolve asset safely — it may be a dangling reference if the asset was deleted
        try:
            asset  = item.asset          # triggers dereference; raises DoesNotExist if gone
            sn     = (asset.serial_number or '') if asset else ''
            model  = (asset.model         or '') if asset else ''
            try:
                atype = asset.asset_type.name if asset and asset.asset_type else ''
            except Exception:
                atype = ''
        except Exception:
            sn, model, atype = '[נמחק]', '', ''

        unit_usd = float(item.unit_price_usd) if item.unit_price_usd else 0.0
        unit_ils = round(unit_usd * rate * factor * 1.18, 2)
        line_ils = round(unit_ils * item.quantity, 2)
        w.writerow([sn, model, atype, item.quantity,
                    f'{unit_usd:.2f}', f'{unit_ils:.2f}', f'{line_ils:.2f}'])
    w.writerow([])
    w.writerow(['', '', '', '', '', 'TOTAL (ILS)', estimate.formatted_total.replace(' ₪', '')])
    from werkzeug.utils import secure_filename
    # secure_filename strips non-ASCII (e.g. Hebrew) → apply fallback AFTER the call
    safe_name = secure_filename(estimate.task_name.replace(' ', '_')) or 'estimate'
    filename  = f"estimate_{safe_name}_{estimate.created_date or 'unknown'}.csv"
    return Response(buf.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename="{filename}"'})


@estimates_bp.route('/<id>/warehouse-receive', methods=['POST'])
@login_required
def warehouse_receive(id):
    if not current_user.is_warehouse and not current_user.is_admin:
        abort(403)
    estimate = get_or_404(Estimate, id)
    estimate.warehouse_status = 'received'
    estimate.save()
    flash('ההזמנה סומנה כהתקבלה.', 'success')
    return redirect(url_for('estimates.detail', id=str(estimate.id)))


@estimates_bp.route('/<id>/warehouse-complete', methods=['POST'])
@login_required
def warehouse_complete(id):
    if not current_user.is_warehouse and not current_user.is_admin:
        abort(403)
    estimate = get_or_404(Estimate, id)
    estimate.warehouse_status = 'completed'
    estimate.warehouse_completed_at = datetime.now(timezone(timedelta(hours=3))).replace(tzinfo=None)
    estimate.save()
    flash('ההזמנה סומנה כבוצעה ועברה להיסטוריה.', 'success')
    return redirect(url_for('estimates.list_estimates'))


@estimates_bp.route('/warehouse-history')
@login_required
def warehouse_history():
    if not current_user.is_warehouse and not current_user.is_admin:
        abort(403)
    estimates = list(
        Estimate.objects(record_type__ne='estimate', warehouse_status='completed').order_by('-warehouse_completed_at')
    )
    return render_template('estimates/warehouse_history.html', estimates=estimates)


@estimates_bp.route('/<id>/convert-to-allocation', methods=['POST'])
@login_required
def convert_to_allocation(id):
    if not current_user.is_super_admin:
        abort(403)
    estimate = get_or_404(Estimate, id)
    estimate.record_type = 'allocation'
    estimate.save()
    flash(f'Estimate "{estimate.task_name}" transferred to allocations list.', 'success')
    return redirect(url_for('estimates.list_estimates'))


@estimates_bp.route('/<id>/delete', methods=['POST'])
@login_required
def delete(id):
    if not current_user.is_admin:
        abort(403)
    estimate = get_or_404(Estimate, id)
    name = estimate.task_name
    estimate.delete()
    flash(f'Estimate "{name}" deleted.', 'info')
    return redirect(url_for('estimates.list_estimates'))
