from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, TextAreaField, DateField, SubmitField
from wtforms.validators import DataRequired, Optional, Length
from datetime import date, timedelta

from app import db
from app.models.asset import Asset, AssetType, AssetEvent
from app.models.site import Site
from app.models.user import User
from app.utils.events import log_event

assets_bp = Blueprint('assets', __name__, url_prefix='/assets')


# ── Forms ────────────────────────────────────────────────────────────────────

def _site_choices():
    return [(0, '— None —')] + [(s.id, s.name) for s in Site.query.order_by(Site.name).all()]


def _user_choices():
    return [(0, '— None —')] + [(u.id, u.name) for u in User.query.order_by(User.name).all()]


def _type_choices():
    return [(t.id, f'{t.name} ({t.category})') for t in AssetType.query.order_by(AssetType.name).all()]


class AssetForm(FlaskForm):
    serial_number = StringField('מספר סידורי', validators=[DataRequired(), Length(max=100)])
    barcode = StringField('ברקוד', validators=[Optional(), Length(max=100)])
    asset_type_id = SelectField('סוג ציוד', coerce=int, validators=[DataRequired()])
    model = StringField('דגם', validators=[Optional(), Length(max=150)])
    manufacturer = StringField('יצרן', validators=[Optional(), Length(max=150)])
    status = SelectField('סטטוס', choices=[
        ('in_storage', 'באחסון'), ('in_use', 'בשימוש'), ('dismantled', 'פורק'),
        ('assigned', 'מוקצה'), ('faulty', 'פגום'), ('retired', 'הוצא משירות'),
    ])
    current_site_id = SelectField('אתר נוכחי', coerce=int, validators=[Optional()])
    assigned_to_id = SelectField('מוקצה ל', coerce=int, validators=[Optional()])
    due_date = DateField('תאריך יעד', validators=[Optional()])
    notes = TextAreaField('הערות', validators=[Optional()])
    submit = SubmitField('שמור ציוד')

    def populate_choices(self):
        self.asset_type_id.choices = _type_choices()
        self.current_site_id.choices = _site_choices()
        self.assigned_to_id.choices = _user_choices()


class DismantleForm(FlaskForm):
    from_site_id = SelectField('פורק מ', coerce=int, validators=[Optional()])
    notes = TextAreaField('הערות', validators=[Optional()])
    submit = SubmitField('אשר פירוק')

    def populate_choices(self):
        self.from_site_id.choices = _site_choices()


class AssignForm(FlaskForm):
    assigned_to_id = SelectField('הקצה ל', coerce=int, validators=[DataRequired()])
    to_site_id = SelectField('פרוס לאתר', coerce=int, validators=[Optional()])
    due_date = DateField('תאריך החזרה', validators=[Optional()])
    notes = TextAreaField('הערות', validators=[Optional()])
    submit = SubmitField('אשר הקצאה')

    def populate_choices(self):
        self.assigned_to_id.choices = [(u.id, u.name) for u in User.query.order_by(User.name).all()]
        self.to_site_id.choices = _site_choices()


class MoveForm(FlaskForm):
    to_site_id = SelectField('העבר לאתר', coerce=int, validators=[DataRequired()])
    notes = TextAreaField('הערות', validators=[Optional()])
    submit = SubmitField('אשר העברה')

    def populate_choices(self):
        self.to_site_id.choices = [(s.id, s.name) for s in Site.query.order_by(Site.name).all()]


class ReturnForm(FlaskForm):
    to_site_id = SelectField('החזר לאתר (אחסון)', coerce=int, validators=[Optional()])
    notes = TextAreaField('הערות', validators=[Optional()])
    submit = SubmitField('אשר החזרה')

    def populate_choices(self):
        self.to_site_id.choices = _site_choices()


class RetireForm(FlaskForm):
    submit = SubmitField('הוצא משירות')


# ── List ─────────────────────────────────────────────────────────────────────

@assets_bp.route('/')
@login_required
def list_assets():
    q = request.args.get('q', '').strip()
    status_filter = request.args.get('status', '')
    type_filter = request.args.get('type', type=int)
    site_filter = request.args.get('site', type=int)
    due_filter = request.args.get('due', '')
    sort = request.args.get('sort', 'created_at')
    order = request.args.get('order', 'desc')

    query = Asset.query

    if q:
        query = query.filter(
            db.or_(Asset.serial_number.ilike(f'%{q}%'), Asset.model.ilike(f'%{q}%'))
        )
    if status_filter:
        query = query.filter(Asset.status == status_filter)
    if type_filter:
        query = query.filter(Asset.asset_type_id == type_filter)
    if site_filter:
        query = query.filter(Asset.current_site_id == site_filter)

    today = date.today()
    if due_filter == 'overdue':
        query = query.filter(Asset.due_date < today, Asset.status != 'retired')
    elif due_filter == 'soon':
        query = query.filter(Asset.due_date >= today, Asset.due_date <= today + timedelta(days=7))

    sort_col = {
        'serial_number': Asset.serial_number,
        'due_date': Asset.due_date,
        'status': Asset.status,
        'created_at': Asset.created_at,
    }.get(sort, Asset.created_at)

    if order == 'asc':
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    assets = query.all()
    asset_types = AssetType.query.order_by(AssetType.name).all()
    sites = Site.query.order_by(Site.name).all()

    return render_template(
        'assets/list.html',
        assets=assets,
        asset_types=asset_types,
        sites=sites,
        q=q,
        status_filter=status_filter,
        type_filter=type_filter,
        site_filter=site_filter,
        due_filter=due_filter,
        sort=sort,
        order=order,
        today=today,
    )


# ── Create ───────────────────────────────────────────────────────────────────

@assets_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_asset():
    if not current_user.can_edit:
        abort(403)
    form = AssetForm()
    form.populate_choices()

    if request.method == 'GET':
        prefill = request.args.get('serial', '').strip().upper()
        if prefill:
            form.serial_number.data = prefill

    if form.validate_on_submit():
        existing = Asset.query.filter_by(serial_number=form.serial_number.data.strip().upper()).first()
        if existing:
            flash(f'מספר סידורי כבר קיים: <a href="{url_for("assets.detail", id=existing.id)}">'
                  f'{existing.serial_number}</a>', 'danger')
        else:
            asset = Asset(
                serial_number=form.serial_number.data.strip().upper(),
                barcode=(form.barcode.data or '').strip() or None,
                asset_type_id=form.asset_type_id.data,
                model=(form.model.data or '').strip() or None,
                manufacturer=(form.manufacturer.data or '').strip() or None,
                status=form.status.data,
                current_site_id=form.current_site_id.data or None,
                assigned_to_id=form.assigned_to_id.data or None,
                due_date=form.due_date.data,
                notes=(form.notes.data or '').strip() or None,
            )
            db.session.add(asset)
            db.session.flush()  # get asset.id before logging event

            log_event(asset, 'created', current_user,
                      to_site=asset.current_site,
                      notes=f'Asset registered. Status: {asset.status_label}')
            db.session.commit()
            flash(f'הציוד {asset.serial_number} נרשם בהצלחה.', 'success')
            return redirect(url_for('assets.detail', id=asset.id))

    return render_template('assets/form.html', form=form, asset=None, title='Register New Asset')


# ── Detail ───────────────────────────────────────────────────────────────────

@assets_bp.route('/<int:id>')
@login_required
def detail(id):
    asset = Asset.query.get_or_404(id)
    events = AssetEvent.query.filter_by(asset_id=id).order_by(AssetEvent.event_date.desc()).all()

    dismantle_form = DismantleForm(prefix='dismantle')
    dismantle_form.populate_choices()
    if asset.current_site_id:
        dismantle_form.from_site_id.data = asset.current_site_id

    assign_form = AssignForm(prefix='assign')
    assign_form.populate_choices()

    move_form = MoveForm(prefix='move')
    move_form.populate_choices()

    return_form = ReturnForm(prefix='ret')
    return_form.populate_choices()
    retire_form = RetireForm(prefix='retire')

    return render_template(
        'assets/detail.html',
        asset=asset,
        events=events,
        dismantle_form=dismantle_form,
        assign_form=assign_form,
        move_form=move_form,
        return_form=return_form,
        retire_form=retire_form,
        today=date.today(),
    )


# ── Edit ─────────────────────────────────────────────────────────────────────

@assets_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    if not current_user.can_edit:
        abort(403)
    asset = Asset.query.get_or_404(id)
    form = AssetForm(obj=asset)
    form.populate_choices()

    if form.validate_on_submit():
        old_status = asset.status
        asset.serial_number = form.serial_number.data.strip().upper()
        asset.barcode = (form.barcode.data or '').strip() or None
        asset.asset_type_id = form.asset_type_id.data
        asset.model = (form.model.data or '').strip() or None
        asset.manufacturer = (form.manufacturer.data or '').strip() or None
        asset.status = form.status.data
        asset.current_site_id = form.current_site_id.data or None
        asset.assigned_to_id = form.assigned_to_id.data or None
        asset.due_date = form.due_date.data
        asset.notes = (form.notes.data or '').strip() or None

        if old_status != asset.status:
            log_event(asset, 'status_change', current_user,
                      notes=f'Status changed: {old_status} → {asset.status}')

        db.session.commit()
        flash('הציוד עודכן בהצלחה.', 'success')
        return redirect(url_for('assets.detail', id=asset.id))

    return render_template('assets/form.html', form=form, asset=asset, title='Edit Asset')


# ── Actions ──────────────────────────────────────────────────────────────────

@assets_bp.route('/<int:id>/dismantle', methods=['POST'])
@login_required
def dismantle(id):
    if not current_user.can_edit:
        abort(403)
    asset = Asset.query.get_or_404(id)
    form = DismantleForm(prefix='dismantle')
    form.populate_choices()

    if form.validate_on_submit():
        from_site = Site.query.get(form.from_site_id.data) if form.from_site_id.data else asset.current_site
        prev_site_id = asset.current_site_id
        asset.status = 'dismantled'
        asset.assigned_to_id = None
        asset.current_site_id = None
        log_event(asset, 'dismantled', current_user,
                  from_site=from_site,
                  notes=(form.notes.data or '').strip() or None)
        db.session.commit()
        flash(f'{asset.serial_number} סומן כפורק.', 'warning')
    else:
        flash('שגיאה בטופס. נסה שוב.', 'danger')

    return redirect(url_for('assets.detail', id=id))


@assets_bp.route('/<int:id>/assign', methods=['POST'])
@login_required
def assign(id):
    if not current_user.can_edit:
        abort(403)
    asset = Asset.query.get_or_404(id)
    form = AssignForm(prefix='assign')
    form.populate_choices()

    if form.validate_on_submit():
        to_site = Site.query.get(form.to_site_id.data) if form.to_site_id.data else None
        prev_site = asset.current_site
        asset.status = 'assigned'
        asset.assigned_to_id = form.assigned_to_id.data
        asset.due_date = form.due_date.data
        if to_site:
            asset.current_site_id = to_site.id
        log_event(asset, 'assigned', current_user,
                  from_site=prev_site,
                  to_site=to_site,
                  notes=(form.notes.data or '').strip() or None)
        db.session.commit()
        flash(f'{asset.serial_number} הוקצה בהצלחה.', 'success')
    else:
        flash('שגיאה בטופס. נסה שוב.', 'danger')

    return redirect(url_for('assets.detail', id=id))


@assets_bp.route('/<int:id>/move', methods=['POST'])
@login_required
def move(id):
    if not current_user.can_edit:
        abort(403)
    asset = Asset.query.get_or_404(id)
    form = MoveForm(prefix='move')
    form.populate_choices()

    if form.validate_on_submit():
        to_site = Site.query.get_or_404(form.to_site_id.data)
        prev_site = asset.current_site
        asset.current_site_id = to_site.id
        log_event(asset, 'moved', current_user,
                  from_site=prev_site,
                  to_site=to_site,
                  notes=(form.notes.data or '').strip() or None)
        db.session.commit()
        flash(f'{asset.serial_number} הועבר ל{to_site.name}.', 'success')
    else:
        flash('שגיאה בטופס. נסה שוב.', 'danger')

    return redirect(url_for('assets.detail', id=id))


@assets_bp.route('/<int:id>/return', methods=['POST'])
@login_required
def return_asset(id):
    if not current_user.can_edit:
        abort(403)
    asset = Asset.query.get_or_404(id)
    form = ReturnForm(prefix='ret')
    form.populate_choices()

    if form.validate_on_submit():
        to_site = Site.query.get(form.to_site_id.data) if form.to_site_id.data else None
        prev_site = asset.current_site
        asset.status = 'in_storage'
        asset.assigned_to_id = None
        asset.due_date = None
        if to_site:
            asset.current_site_id = to_site.id
        log_event(asset, 'returned', current_user,
                  from_site=prev_site,
                  to_site=to_site,
                  notes=(form.notes.data or '').strip() or None)
        db.session.commit()
        flash(f'{asset.serial_number} הוחזר לאחסון.', 'info')
    else:
        flash('שגיאה בטופס. נסה שוב.', 'danger')

    return redirect(url_for('assets.detail', id=id))


@assets_bp.route('/<int:id>/retire', methods=['POST'])
@login_required
def retire(id):
    if not current_user.can_edit:
        abort(403)
    asset = Asset.query.get_or_404(id)
    asset.status = 'retired'
    asset.assigned_to_id = None
    asset.due_date = None
    log_event(asset, 'retired', current_user)
    db.session.commit()
    flash(f'{asset.serial_number} הוצא משירות.', 'secondary')
    return redirect(url_for('assets.detail', id=id))
