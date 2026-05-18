import csv
import io
import json
from datetime import date, timedelta

from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, Response
from flask_login import login_required, current_user
from sqlalchemy import func

from app import db
from app.models.estimate import Estimate, EstimateItem
from app.models.asset import Asset
from app.models.settings import AppSetting

estimates_bp = Blueprint('estimates', __name__, url_prefix='/estimates')


@estimates_bp.route('/')
@login_required
def list_estimates():
    estimates = (Estimate.query
                 .filter_by(status='pending')
                 .order_by(Estimate.created_at.desc())
                 .all())
    return render_template('estimates/list.html', estimates=estimates)


@estimates_bp.route('/history')
@login_required
def history():
    estimates = (Estimate.query
                 .filter_by(status='withdrawn')
                 .order_by(Estimate.created_at.desc())
                 .all())
    return render_template('estimates/history.html', estimates=estimates)


@estimates_bp.route('/<int:id>/withdraw', methods=['POST'])
@login_required
def withdraw(id):
    estimate = Estimate.query.get_or_404(id)
    estimate.status = 'withdrawn'
    db.session.commit()
    flash(f'Assignment {estimate.allocation_number} marked as ongoing and moved to History.', 'success')
    return redirect(url_for('estimates.detail', id=id))


@estimates_bp.route('/<int:id>/restore', methods=['POST'])
@login_required
def restore(id):
    estimate = Estimate.query.get_or_404(id)
    estimate.status = 'pending'
    db.session.commit()
    flash(f'Assignment {estimate.allocation_number} restored to Pending.', 'success')
    return redirect(url_for('estimates.detail', id=id))


@estimates_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_estimate():
    usd_rate = AppSetting.get('usd_rate') or 3.0
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

        last_num = db.session.query(func.max(Estimate.allocation_number)).scalar()
        next_num = (last_num or 0) + 1

        estimate = Estimate(
            allocation_number=next_num,
            task_name=task_name,
            project_name=project_name or None,
            created_date=today,
            valid_until=validity,
            usd_rate=usd_rate,
            created_by_id=current_user.id,
        )
        db.session.add(estimate)
        db.session.flush()

        total_nis = 0.0
        for item in items_data:
            try:
                asset_id = int(item['asset_id'])
                qty      = max(1, int(item.get('quantity', 1)))
            except (KeyError, ValueError, TypeError):
                continue
            asset = Asset.query.get(asset_id)
            if not asset or not asset.price_usd:
                continue
            unit_usd = float(asset.price_usd)
            line_nis = round(unit_usd * float(usd_rate) * 1.7 * 1.18 * qty, 2)
            total_nis += line_nis
            db.session.add(EstimateItem(
                estimate_id=estimate.id,
                asset_id=asset_id,
                quantity=qty,
                unit_price_usd=unit_usd,
            ))

        estimate.total_nis = round(total_nis, 2)
        db.session.commit()
        flash(f'Estimate "{task_name}" saved successfully.', 'success')
        return redirect(url_for('estimates.list_estimates'))

    # Build asset catalogue for JS selector (only assets with a USD price)
    assets = (Asset.query
              .filter(Asset.price_usd.isnot(None))
              .order_by(Asset.serial_number)
              .all())
    assets_json = json.dumps([{
        'id':           a.id,
        'component_id': a.component_id or '',
        'serial_number': a.serial_number,
        'model':        a.model or '',
        'manufacturer': a.manufacturer or '',
        'type':         a.asset_type.name if a.asset_type else '',
        'price_usd':    float(a.price_usd),
        'quantity':     a.quantity if a.quantity is not None else 0,
    } for a in assets])

    return render_template('estimates/new.html',
                           assets_json=assets_json,
                           usd_rate=float(usd_rate),
                           today=today,
                           valid_until=validity)


@estimates_bp.route('/<int:id>')
@login_required
def detail(id):
    estimate = Estimate.query.get_or_404(id)
    return render_template('estimates/detail.html', estimate=estimate)


@estimates_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    estimate = Estimate.query.get_or_404(id)
    usd_rate = float(estimate.usd_rate)

    if request.method == 'POST':
        task_name    = (request.form.get('task_name') or '').strip()
        project_name = (request.form.get('project_name') or '').strip()
        items_raw    = request.form.get('items_json', '[]')

        if not task_name:
            flash('Requester name is required.', 'danger')
            return redirect(url_for('estimates.edit', id=id))

        try:
            items_data = json.loads(items_raw)
        except (json.JSONDecodeError, TypeError):
            items_data = []

        estimate.task_name    = task_name
        estimate.project_name = project_name or None

        for item in list(estimate.items):
            db.session.delete(item)
        db.session.flush()

        total_nis = 0.0
        for item in items_data:
            try:
                asset_id = int(item['asset_id'])
                qty      = max(1, int(item.get('quantity', 1)))
            except (KeyError, ValueError, TypeError):
                continue
            asset = Asset.query.get(asset_id)
            if not asset or not asset.price_usd:
                continue
            unit_usd = float(asset.price_usd)
            line_nis = round(unit_usd * usd_rate * 1.7 * 1.18 * qty, 2)
            total_nis += line_nis
            db.session.add(EstimateItem(
                estimate_id=estimate.id,
                asset_id=asset_id,
                quantity=qty,
                unit_price_usd=unit_usd,
            ))

        estimate.total_nis = round(total_nis, 2)
        db.session.commit()
        flash('Estimate updated successfully.', 'success')
        return redirect(url_for('estimates.detail', id=id))

    assets = (Asset.query
              .filter(Asset.price_usd.isnot(None))
              .order_by(Asset.serial_number)
              .all())
    assets_json = json.dumps([{
        'id':            a.id,
        'component_id':  a.component_id or '',
        'serial_number': a.serial_number,
        'model':         a.model or '',
        'manufacturer':  a.manufacturer or '',
        'type':          a.asset_type.name if a.asset_type else '',
        'price_usd':     float(a.price_usd),
        'quantity':      a.quantity if a.quantity is not None else 0,
    } for a in assets])

    selected_json = json.dumps([{
        'asset_id': item.asset_id,
        'quantity': item.quantity,
    } for item in estimate.items])

    return render_template('estimates/edit.html',
                           estimate=estimate,
                           assets_json=assets_json,
                           selected_json=selected_json,
                           usd_rate=usd_rate)


@estimates_bp.route('/<int:id>/export.csv')
@login_required
def export_csv(id):
    estimate = Estimate.query.get_or_404(id)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['Allocation Number', estimate.allocation_number or ''])
    w.writerow(['Requester Name', estimate.task_name])
    w.writerow(['Project', estimate.project_name or ''])
    w.writerow(['Date', estimate.created_date.strftime('%d %b %Y')])
    w.writerow(['Valid Until', estimate.valid_until.strftime('%d %b %Y')])
    w.writerow([])
    w.writerow(['Part No.', 'Description', 'Type', 'Qty', 'Unit Price (USD)', 'Unit Price (ILS)', 'Line Total (ILS)'])
    rate = float(estimate.usd_rate)
    for item in estimate.items:
        unit_usd = float(item.unit_price_usd) if item.unit_price_usd else 0.0
        unit_ils = round(unit_usd * rate * 1.7 * 1.18, 2)
        line_ils = round(unit_ils * item.quantity, 2)
        w.writerow([
            item.asset.serial_number if item.asset else '',
            item.asset.model if item.asset else '',
            item.asset.asset_type.name if item.asset and item.asset.asset_type else '',
            item.quantity,
            f'{unit_usd:.2f}',
            f'{unit_ils:.2f}',
            f'{line_ils:.2f}',
        ])
    w.writerow([])
    w.writerow(['', '', '', '', '', 'TOTAL (ILS)', estimate.formatted_total.replace(' ₪', '')])
    filename = f"estimate_{estimate.task_name.replace(' ', '_')}_{estimate.created_date}.csv"
    return Response(
        buf.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


@estimates_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    if not current_user.is_admin:
        abort(403)
    estimate = Estimate.query.get_or_404(id)
    name = estimate.task_name
    db.session.delete(estimate)
    db.session.commit()
    flash(f'Estimate "{name}" deleted.', 'info')
    return redirect(url_for('estimates.list_estimates'))
