import csv
import io
import json
from datetime import date, timedelta

from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, Response, jsonify
from flask_login import login_required, current_user

from app.models.estimate import Estimate, EstimateItem
from app.models.asset import Asset
from app.models.settings import AppSetting
from app.utils.mongo_helpers import get_or_404

estimates_bp = Blueprint('estimates', __name__, url_prefix='/estimates')


def _next_allocation_number():
    used = {e.allocation_number for e in Estimate.objects(allocation_number__exists=True) if e.allocation_number}
    if not used:
        return 1001
    n = min(used)
    while n in used:
        n += 1
    return n


@estimates_bp.route('/')
@login_required
def list_estimates():
    estimates = list(Estimate.objects(status='pending').order_by('-created_at'))
    return render_template('estimates/list.html', estimates=estimates)


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
    from app.models.settings import EFFECTIVE_RATE
    usd_rate = EFFECTIVE_RATE  # 3.6 × 1.048 ≈ 3.7728
    today    = date.today()
    validity = today + timedelta(days=90)

    if request.method == 'POST':
        task_name    = (request.form.get('task_name') or '').strip()
        project_name = (request.form.get('project_name') or '').strip()
        items_raw    = request.form.get('items_json', '[]')

        if not task_name:
            flash('Task name is required.', 'danger')
            return redirect(url_for('estimates.new_estimate'))

        try:
            items_data = json.loads(items_raw)
        except (json.JSONDecodeError, TypeError):
            items_data = []

        alloc_raw = (request.form.get('allocation_number') or '').strip()
        next_num  = int(alloc_raw) if alloc_raw.isdigit() and int(alloc_raw) > 0 else _next_allocation_number()

        conflict = Estimate.objects(allocation_number=next_num).first()
        if conflict:
            flash(
                f'Allocation number {next_num} is already in use '
                f'(assigned to "{conflict.task_name}"). Please choose a different number.',
                'danger',
            )
            return redirect(url_for('estimates.new_estimate'))

        maint_factor = float(AppSetting.get('maintenance_factor') or 1.7)
        estimate = Estimate(
            allocation_number=next_num,
            task_name=task_name,
            project_name=project_name or None,
            created_date=today,
            valid_until=validity,
            usd_rate=usd_rate,
            maintenance_factor=maint_factor,
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

        estimate.total_nis = round(total_nis, 2)
        estimate.save()
        flash(f'Estimate "{task_name}" saved successfully.', 'success')
        return redirect(url_for('estimates.list_estimates'))

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

    next_num     = _next_allocation_number()
    maint_factor = float(AppSetting.get('maintenance_factor') or 1.7)
    return render_template('estimates/new.html',
                           assets_json=assets_json, usd_rate=float(usd_rate),
                           maint_factor=maint_factor,
                           today=today, valid_until=validity, next_num=next_num)


@estimates_bp.route('/<id>')
@login_required
def detail(id):
    estimate = get_or_404(Estimate, id)
    return render_template('estimates/detail.html', estimate=estimate)


@estimates_bp.route('/<id>/withdraw', methods=['POST'])
@login_required
def withdraw(id):
    estimate = get_or_404(Estimate, id)
    estimate.status = 'withdrawn'
    estimate.save()
    flash(f'Assignment {estimate.allocation_number} marked as ongoing and moved to History.', 'success')
    return redirect(url_for('estimates.detail', id=str(estimate.id)))


@estimates_bp.route('/<id>/restore', methods=['POST'])
@login_required
def restore(id):
    estimate = get_or_404(Estimate, id)
    estimate.status = 'pending'
    estimate.save()
    flash(f'Assignment {estimate.allocation_number} restored to Pending.', 'success')
    return redirect(url_for('estimates.detail', id=str(estimate.id)))


@estimates_bp.route('/<id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
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

        estimate.total_nis = round(total_nis, 2)
        estimate.save()
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
    w.writerow(['Date', estimate.created_date.strftime('%d %b %Y')])
    w.writerow(['Valid Until', estimate.valid_until.strftime('%d %b %Y')])
    w.writerow([])
    w.writerow(['Part No.','Description','Type','Qty','Unit Price (USD)','Unit Price (ILS)','Line Total (ILS)'])
    rate   = float(estimate.usd_rate)
    factor = float(estimate.maintenance_factor or 1.7)
    for item in estimate.items:
        unit_usd = float(item.unit_price_usd) if item.unit_price_usd else 0.0
        unit_ils = round(unit_usd * rate * factor * 1.18, 2)
        line_ils = round(unit_ils * item.quantity, 2)
        w.writerow([
            item.asset.serial_number if item.asset else '',
            item.asset.model if item.asset else '',
            item.asset.asset_type.name if item.asset and item.asset.asset_type else '',
            item.quantity,
            f'{unit_usd:.2f}', f'{unit_ils:.2f}', f'{line_ils:.2f}',
        ])
    w.writerow([])
    w.writerow(['', '', '', '', '', 'TOTAL (ILS)', estimate.formatted_total.replace(' ₪', '')])
    filename = f"estimate_{estimate.task_name.replace(' ', '_')}_{estimate.created_date}.csv"
    return Response(buf.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename="{filename}"'})


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
