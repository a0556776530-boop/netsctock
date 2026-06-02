from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, jsonify, g
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, DecimalField, TextAreaField, SelectField, SubmitField
from wtforms.validators import DataRequired, Optional, Length, NumberRange
from mongoengine import Q

from app.models.pool import Pool, PoolTransaction
from app.models.estimate import Estimate
from app.utils.mongo_helpers import get_or_404

pools_bp = Blueprint('pools', __name__, url_prefix='/pools')


class PoolForm(FlaskForm):
    name         = StringField('Pool Name',    validators=[DataRequired(), Length(max=200)])
    emf_number   = StringField('EMF Number',   validators=[DataRequired(), Length(max=50)])
    total_amount = DecimalField('Total Amount', validators=[DataRequired(), NumberRange(min=0.01)], places=2)
    currency     = SelectField('Currency',     choices=[('ILS', '₪ ILS'), ('USD', '$ USD')])
    notes        = TextAreaField('Notes',      validators=[Optional()])
    submit       = SubmitField('Save')


# ── List ──────────────────────────────────────────────────────────────────────

@pools_bp.route('/')
@login_required
def list_pools():
    pools = list(Pool.objects.order_by('-created_at'))
    return render_template('pools/list.html', pools=pools)


# ── Create ────────────────────────────────────────────────────────────────────

@pools_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_pool():
    if not current_user.can_edit:
        abort(403)
    form = PoolForm()
    if form.validate_on_submit():
        emf = form.emf_number.data.strip()
        if Pool.objects(emf_number=emf).first():
            flash('מספר EMF כבר קיים במערכת.', 'danger')
        else:
            Pool(
                name=form.name.data.strip(),
                emf_number=emf,
                total_amount=float(form.total_amount.data),
                currency=form.currency.data,
                notes=form.notes.data.strip() if form.notes.data else '',
                created_by=current_user._get_current_object(),
            ).save()
            flash('פול נוצר בהצלחה.', 'success')
            return redirect(url_for('pools.list_pools'))
    return render_template('pools/form.html', form=form, pool=None)


# ── Detail ────────────────────────────────────────────────────────────────────

@pools_bp.route('/<id>')
@login_required
def detail(id):
    pool = get_or_404(Pool, id)
    return render_template('pools/detail.html', pool=pool)


# ── Edit ──────────────────────────────────────────────────────────────────────

@pools_bp.route('/<id>/edit', methods=['GET', 'POST'])
@login_required
def edit_pool(id):
    if not current_user.can_edit:
        abort(403)
    pool = get_or_404(Pool, id)
    form = PoolForm(obj=pool)
    if form.validate_on_submit():
        new_emf = form.emf_number.data.strip()
        conflict = Pool.objects(emf_number=new_emf).exclude(id=pool.id).first()
        if conflict:
            flash(f'מספר EMF "{new_emf}" כבר קיים בפול אחר.', 'danger')
            return render_template('pools/form.html', form=form, pool=pool)

        pool.name         = form.name.data.strip()
        pool.emf_number   = new_emf
        pool.total_amount = float(form.total_amount.data)
        pool.currency     = form.currency.data
        pool.notes        = form.notes.data.strip() if form.notes.data else ''
        pool.save()
        flash('פול עודכן.', 'success')
        return redirect(url_for('pools.detail', id=pool.id))
    return render_template('pools/form.html', form=form, pool=pool)


# ── Delete ────────────────────────────────────────────────────────────────────

@pools_bp.route('/<id>/delete', methods=['POST'])
@login_required
def delete_pool(id):
    if not current_user.can_edit:
        abort(403)
    pool = get_or_404(Pool, id)
    if pool.transactions:
        flash(
            f'לא ניתן למחוק את הפול — יש לו {len(pool.transactions)} עסקאות מקושרות. בטל אותן תחילה.',
            'danger'
        )
        return redirect(url_for('pools.detail', id=id))
    pool.delete()
    flash('פול נמחק.', 'success')
    return redirect(url_for('pools.list_pools'))


# ── Estimate search API ───────────────────────────────────────────────────────

@pools_bp.route('/api/search-estimates')
@login_required
def search_estimates():
    if not current_user.can_edit:
        abort(403)
    q = request.args.get('q', '').strip()

    base = Q(status='pending') & Q(record_type__ne='estimate')

    if len(q) >= 2:
        search = Q(task_name__icontains=q) | Q(project_name__icontains=q)
        try:
            search = search | Q(allocation_number=int(q))
        except ValueError:
            pass
        base = base & search

    results = []
    for e in Estimate.objects(base).order_by('-allocation_number').limit(100):
        results.append({
            'id':                str(e.id),
            'task_name':         e.task_name,
            'project_name':      e.project_name or '',
            'allocation_number': e.allocation_number,
            'total_nis':         round(e.total_nis or 0, 2),
            'total_usd':         round(e.total_usd or 0, 2),
            'status':            e.status,
        })
    return jsonify(results)


# ── Link estimate → draw from pool ───────────────────────────────────────────

@pools_bp.route('/<id>/link', methods=['POST'])
@login_required
def link_estimate(id):
    if not current_user.can_edit:
        abort(403)

    pool        = get_or_404(Pool, id)
    estimate_id = request.form.get('estimate_id', '').strip()
    notes       = request.form.get('notes', '').strip()

    if not estimate_id:
        flash('לא נבחרה הקצאה.', 'danger')
        return redirect(url_for('pools.detail', id=id))

    estimate = Estimate.objects(id=estimate_id).first()
    if not estimate:
        flash('הקצאה לא נמצאה.', 'danger')
        return redirect(url_for('pools.detail', id=id))

    # Guard: already linked
    for tx in pool.transactions:
        try:
            if str(tx.estimate.id) == estimate_id:
                flash('הקצאה זו כבר מקושרת לפול זה.', 'warning')
                return redirect(url_for('pools.detail', id=id))
        except Exception:
            pass

    from app.utils.exchange import get_usd_to_nis
    usd_rate = get_usd_to_nis()

    amount = float(estimate.total_nis or 0) if pool.currency == 'ILS' else float(estimate.total_usd or 0)

    if amount <= 0:
        flash('להקצאה אין סכום לחיוב.', 'danger')
        return redirect(url_for('pools.detail', id=id))

    if amount > pool.balance:
        flash(
            f'יתרה לא מספיקה. יתרת הפול: {pool.fmt(pool.balance)} | נדרש: {pool.fmt(amount)}',
            'danger'
        )
        return redirect(url_for('pools.detail', id=id))

    tx = PoolTransaction(
        estimate=estimate,
        amount_drawn=amount,
        currency=pool.currency,
        exchange_rate=usd_rate,
        created_by=current_user._get_current_object(),
        notes=notes,
    )

    # Single atomic operation: increment consumed_amount AND push transaction
    # If balance check fails → nothing changes. If it succeeds → both fields update together.
    matched = Pool.objects(
        id=pool.id,
        consumed_amount__lte=pool.total_amount - amount
    ).update_one(inc__consumed_amount=amount, push__transactions=tx)

    if not matched:
        flash('יתרה לא מספיקה (עדכון מקביל). נסה שוב.', 'danger')
        return redirect(url_for('pools.detail', id=id))

    flash(f'הקצאה קושרה. חויב {pool.fmt(amount)} מהפול.', 'success')
    return redirect(url_for('pools.detail', id=id))


# ── Unlink estimate → refund to pool ─────────────────────────────────────────

@pools_bp.route('/<id>/unlink/<int:tx_index>', methods=['POST'])
@login_required
def unlink_estimate(id, tx_index):
    if not current_user.can_edit:
        abort(403)

    pool = get_or_404(Pool, id)
    try:
        tx     = pool.transactions[tx_index]
        amount = round(float(tx.amount_drawn), 2)
        est_id = tx.estimate.id

        # Single atomic operation: decrement consumed_amount AND pull transaction
        from bson import ObjectId
        result = Pool._get_collection().update_one(
            {'_id': pool.id},
            {
                '$inc':  {'consumed_amount': -amount},
                '$pull': {'transactions': {'estimate': ObjectId(str(est_id))}},
            }
        )
        if result.modified_count:
            flash(f'קישור בוטל. {pool.fmt(amount)} הוחזרו לפול.', 'success')
        else:
            flash('לא הצלחנו לבטל את הקישור. נסה שוב.', 'danger')
    except (IndexError, AttributeError):
        flash('טרנזקציה לא נמצאה.', 'danger')

    return redirect(url_for('pools.detail', id=id))
