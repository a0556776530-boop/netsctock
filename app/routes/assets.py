import json
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, g
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, TextAreaField, SubmitField, DecimalField, IntegerField
from wtforms.validators import DataRequired, Optional, Length, NumberRange
from collections import defaultdict

from app import db
from app.models.asset import Asset, AssetType, AssetEvent
from app.models.site import Site
from app.models.user import User
from app.utils.events import log_event
from app.utils.translations import localize_form

assets_bp = Blueprint('assets', __name__, url_prefix='/assets')

CATEGORY_ORDER = [
    'Router', 'Aggregation', 'Access Switch', 'SFP', 'Cards',
    'Power Supply', 'Power Cords', 'Console Cables',
]
CATEGORY_LABELS = {
    'Router':         'Routers',
    'Aggregation':    'Aggregation',
    'Access Switch':  'Access Switches',
    'SFP':            'SFP Modules',
    'Cards':          'Cards & Modules',
    'Power Supply':   'Power Supplies',
    'Power Cords':    'Power Cords',
    'Console Cables': 'Console Cables',
}


# ── Forms ────────────────────────────────────────────────────────────────────

def _site_choices():
    return [(0, '— None —')] + [(s.id, s.name) for s in Site.query.order_by(Site.name).all()]


def _user_choices():
    return [(0, '— None —')] + [(u.id, u.name) for u in User.query.order_by(User.name).all()]


def _type_choices():
    return [(t.id, f'{t.name} ({t.category})') for t in AssetType.query.order_by(AssetType.name).all()]


class AssetForm(FlaskForm):
    component_id  = StringField('Asset ID', validators=[Optional(), Length(max=50)])
    serial_number = StringField('Mfr. Part No.', validators=[DataRequired(), Length(max=100)])
    barcode = StringField('Barcode', validators=[Optional(), Length(max=100)])
    asset_type_id = SelectField('Asset Type', coerce=int, validators=[DataRequired()])
    model = StringField('Description', validators=[Optional(), Length(max=150)])
    manufacturer = StringField('Manufacturer', validators=[Optional(), Length(max=150)])
    status = SelectField('Status', choices=[
        ('in_storage', 'In Storage'), ('in_use', 'In Use'), ('dismantled', 'Dismantled'),
        ('assigned', 'Assigned'), ('faulty', 'Faulty'), ('retired', 'Retired'),
    ])
    current_site_id = SelectField('Current Site', coerce=int, validators=[Optional()])
    assigned_to_id = SelectField('Assigned To', coerce=int, validators=[Optional()])
    notes     = TextAreaField('Notes', validators=[Optional()])
    price_usd = DecimalField('Price USD ($)', validators=[Optional(), NumberRange(min=0)], places=0)
    price_nis = DecimalField('Price NIS (₪)', validators=[Optional(), NumberRange(min=0)], places=0)
    quantity       = IntegerField('Stock Qty',       validators=[Optional(), NumberRange(min=0)])
    min_threshold  = IntegerField('Min Threshold',   validators=[Optional(), NumberRange(min=0)])
    submit         = SubmitField('Save Asset')

    def populate_choices(self):
        self.asset_type_id.choices = _type_choices()
        self.current_site_id.choices = _site_choices()
        self.assigned_to_id.choices = _user_choices()


class DismantleForm(FlaskForm):
    from_site_id = SelectField('Dismantled From', coerce=int, validators=[Optional()])
    notes = TextAreaField('Notes', validators=[Optional()])
    submit = SubmitField('Confirm Dismantle')

    def populate_choices(self):
        self.from_site_id.choices = _site_choices()


class AssignForm(FlaskForm):
    assigned_to_id = SelectField('Assign To', coerce=int, validators=[DataRequired()])
    to_site_id = SelectField('Deploy to Site', coerce=int, validators=[Optional()])
    notes = TextAreaField('Notes', validators=[Optional()])
    submit = SubmitField('Confirm Assignment')

    def populate_choices(self):
        self.assigned_to_id.choices = [(u.id, u.name) for u in User.query.order_by(User.name).all()]
        self.to_site_id.choices = _site_choices()


class MoveForm(FlaskForm):
    to_site_id = SelectField('Move to Site', coerce=int, validators=[DataRequired()])
    notes = TextAreaField('Notes', validators=[Optional()])
    submit = SubmitField('Confirm Move')

    def populate_choices(self):
        self.to_site_id.choices = [(s.id, s.name) for s in Site.query.order_by(Site.name).all()]


class ReturnForm(FlaskForm):
    to_site_id = SelectField('Return to Site (Storage)', coerce=int, validators=[Optional()])
    notes = TextAreaField('Notes', validators=[Optional()])
    submit = SubmitField('Confirm Return')

    def populate_choices(self):
        self.to_site_id.choices = _site_choices()


class RetireForm(FlaskForm):
    submit = SubmitField('Retire Asset')


# ── List ─────────────────────────────────────────────────────────────────────

@assets_bp.route('/')
@login_required
def list_assets():
    q = request.args.get('q', '').strip()
    status_filter = request.args.get('status', '')
    type_filter = request.args.get('type', type=int)
    site_filter = request.args.get('site', type=int)
    sort = request.args.get('sort', 'created_at')
    order = request.args.get('order', 'desc')

    query = Asset.query

    if q:
        query = query.filter(
            db.or_(Asset.serial_number.ilike(f'%{q}%'), Asset.model.ilike(f'%{q}%'),
                   Asset.component_id.ilike(f'%{q}%'))
        )
    if status_filter:
        query = query.filter(Asset.status == status_filter)
    if type_filter:
        query = query.filter(Asset.asset_type_id == type_filter)
    if site_filter:
        query = query.filter(Asset.current_site_id == site_filter)

    sort_col = {
        'component_id':  Asset.component_id,
        'serial_number': Asset.serial_number,
        'status':        Asset.status,
        'created_at':    Asset.created_at,
        'price':         Asset.price,
        'price_nis':     Asset.price_nis,
        'price_usd':     Asset.price_usd,
        'quantity':      Asset.quantity,
    }.get(sort, Asset.created_at)

    if order == 'asc':
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    assets = query.all()

    by_type = defaultdict(list)
    for asset in assets:
        by_type[asset.asset_type.name if asset.asset_type else 'Other'].append(asset)

    grouped_assets = []
    seen = set()
    for cat in CATEGORY_ORDER:
        if cat in by_type:
            grouped_assets.append((CATEGORY_LABELS.get(cat, cat), by_type[cat]))
            seen.add(cat)
    for cat, items in by_type.items():
        if cat not in seen:
            grouped_assets.append((cat, items))

    all_types = AssetType.query.all()
    asset_types = sorted(
        all_types,
        key=lambda t: CATEGORY_ORDER.index(t.name) if t.name in CATEGORY_ORDER else len(CATEGORY_ORDER)
    )
    sites = Site.query.order_by(Site.name).all()

    from app.models.settings import AppSetting
    global_settings = json.dumps(AppSetting.all_as_dict())

    # Commitments: sum of quantities in PENDING estimate items per asset
    from app.models.estimate import EstimateItem, Estimate
    from sqlalchemy import func as sa_func
    commitment_rows = (
        db.session.query(EstimateItem.asset_id,
                         sa_func.sum(EstimateItem.quantity).label('total'))
        .join(Estimate, EstimateItem.estimate_id == Estimate.id)
        .filter(Estimate.status == 'pending')
        .group_by(EstimateItem.asset_id)
        .all()
    )
    commitments = {row.asset_id: int(row.total) for row in commitment_rows}

    return render_template(
        'assets/list.html',
        assets=assets,
        grouped_assets=grouped_assets,
        asset_types=asset_types,
        sites=sites,
        q=q,
        status_filter=status_filter,
        type_filter=type_filter,
        site_filter=site_filter,
        sort=sort,
        order=order,
        global_settings=global_settings,
        commitments=commitments,
    )


# ── Create ───────────────────────────────────────────────────────────────────

@assets_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_asset():
    if not current_user.can_edit:
        abort(403)
    t = getattr(g, 't', {})
    form = AssetForm()
    form.populate_choices()
    localize_form(form, t, submit_key='form_save_asset')

    if request.method == 'GET':
        prefill = request.args.get('serial', '').strip().upper()
        if prefill:
            form.serial_number.data = prefill

    if form.validate_on_submit():
        existing = Asset.query.filter_by(serial_number=form.serial_number.data.strip().upper()).first()
        if existing:
            flash(
                t.get('flash_asset_duplicate', 'Model already registered: <a href="{url}">{sn}</a>').format(
                    url=url_for('assets.detail', id=existing.id),
                    sn=existing.serial_number,
                ),
                'danger',
            )
        else:
            asset = Asset(
                component_id=(form.component_id.data or '').strip() or None,
                serial_number=form.serial_number.data.strip().upper(),
                barcode=(form.barcode.data or '').strip() or None,
                asset_type_id=form.asset_type_id.data,
                model=(form.model.data or '').strip() or None,
                manufacturer=(form.manufacturer.data or '').strip() or None,
                status='in_storage',
                current_site_id=None,
                assigned_to_id=None,
                notes=(form.notes.data or '').strip() or None,
                price_usd=form.price_usd.data,
                price_nis=form.price_nis.data,
                quantity=form.quantity.data,
                min_threshold=form.min_threshold.data,
            )
            db.session.add(asset)
            db.session.flush()

            log_event(asset, 'created', current_user,
                      to_site=asset.current_site,
                      notes=f'Asset registered. Status: {asset.status_label}')
            db.session.commit()
            flash(t.get('flash_asset_created', '{sn} registered successfully.').format(sn=asset.serial_number), 'success')
            return redirect(url_for('assets.detail', id=asset.id))

    return render_template('assets/form.html', form=form, asset=None,
                           title=t.get('form_title_register_asset', 'Register New Asset'))


# ── Detail ───────────────────────────────────────────────────────────────────

@assets_bp.route('/<int:id>')
@login_required
def detail(id):
    t = getattr(g, 't', {})
    asset = Asset.query.get_or_404(id)
    events = AssetEvent.query.filter_by(asset_id=id).order_by(AssetEvent.event_date.desc()).all()

    dismantle_form = DismantleForm(prefix='dismantle')
    dismantle_form.populate_choices()
    if asset.current_site_id:
        dismantle_form.from_site_id.data = asset.current_site_id
    localize_form(dismantle_form, t, submit_key='form_confirm_dismantle')

    assign_form = AssignForm(prefix='assign')
    assign_form.populate_choices()
    localize_form(assign_form, t, submit_key='form_confirm_assignment',
                  extra={'to_site_id': 'form_deploy_to_site'})

    move_form = MoveForm(prefix='move')
    move_form.populate_choices()
    localize_form(move_form, t, submit_key='form_confirm_move',
                  extra={'to_site_id': 'form_move_to_site'})

    return_form = ReturnForm(prefix='ret')
    return_form.populate_choices()
    localize_form(return_form, t, submit_key='form_confirm_return',
                  extra={'to_site_id': 'form_return_to_site'})

    retire_form = RetireForm(prefix='retire')
    localize_form(retire_form, t, submit_key='form_retire_asset')

    return render_template(
        'assets/detail.html',
        asset=asset,
        events=events,
        dismantle_form=dismantle_form,
        assign_form=assign_form,
        move_form=move_form,
        return_form=return_form,
        retire_form=retire_form,
    )


# ── Edit ─────────────────────────────────────────────────────────────────────

@assets_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    if not current_user.can_edit:
        abort(403)
    t = getattr(g, 't', {})
    asset = Asset.query.get_or_404(id)
    form = AssetForm(obj=asset)
    form.populate_choices()
    localize_form(form, t, submit_key='form_save_asset')

    if form.validate_on_submit():
        asset.component_id = (form.component_id.data or '').strip() or None
        asset.serial_number = form.serial_number.data.strip().upper()
        asset.barcode = (form.barcode.data or '').strip() or None
        asset.asset_type_id = form.asset_type_id.data
        asset.model = (form.model.data or '').strip() or None
        asset.manufacturer = (form.manufacturer.data or '').strip() or None
        # status / current_site_id / assigned_to_id are managed via action buttons, not this form
        asset.notes          = (form.notes.data or '').strip() or None
        asset.price_usd      = form.price_usd.data
        asset.price_nis      = form.price_nis.data
        asset.quantity       = form.quantity.data
        asset.min_threshold  = form.min_threshold.data

        db.session.commit()
        flash(t.get('flash_asset_updated', 'Asset updated successfully.'), 'success')
        return redirect(url_for('assets.list_assets'))

    return render_template('assets/form.html', form=form, asset=asset,
                           title=t.get('form_title_edit_asset', 'Edit Asset'))


# ── Actions ──────────────────────────────────────────────────────────────────

@assets_bp.route('/<int:id>/dismantle', methods=['POST'])
@login_required
def dismantle(id):
    if not current_user.can_edit:
        abort(403)
    t = getattr(g, 't', {})
    asset = Asset.query.get_or_404(id)
    form = DismantleForm(prefix='dismantle')
    form.populate_choices()

    if form.validate_on_submit():
        from_site = Site.query.get(form.from_site_id.data) if form.from_site_id.data else asset.current_site
        asset.status = 'dismantled'
        asset.assigned_to_id = None
        asset.current_site_id = None
        log_event(asset, 'dismantled', current_user,
                  from_site=from_site,
                  notes=(form.notes.data or '').strip() or None)
        db.session.commit()
        flash(t.get('flash_dismantled', '{sn} marked as dismantled.').format(sn=asset.serial_number), 'warning')
    else:
        flash(t.get('flash_form_error', 'Form error. Please try again.'), 'danger')

    return redirect(url_for('assets.detail', id=id))


@assets_bp.route('/<int:id>/assign', methods=['POST'])
@login_required
def assign(id):
    if not current_user.can_edit:
        abort(403)
    t = getattr(g, 't', {})
    asset = Asset.query.get_or_404(id)
    form = AssignForm(prefix='assign')
    form.populate_choices()

    if form.validate_on_submit():
        to_site = Site.query.get(form.to_site_id.data) if form.to_site_id.data else None
        prev_site = asset.current_site
        asset.status = 'assigned'
        asset.assigned_to_id = form.assigned_to_id.data
        if to_site:
            asset.current_site_id = to_site.id
        log_event(asset, 'assigned', current_user,
                  from_site=prev_site,
                  to_site=to_site,
                  notes=(form.notes.data or '').strip() or None)
        db.session.commit()
        flash(t.get('flash_assigned', '{sn} assigned successfully.').format(sn=asset.serial_number), 'success')
    else:
        flash(t.get('flash_form_error', 'Form error. Please try again.'), 'danger')

    return redirect(url_for('assets.detail', id=id))


@assets_bp.route('/<int:id>/move', methods=['POST'])
@login_required
def move(id):
    if not current_user.can_edit:
        abort(403)
    t = getattr(g, 't', {})
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
        flash(t.get('flash_moved', '{sn} moved to {site}.').format(sn=asset.serial_number, site=to_site.name), 'success')
    else:
        flash(t.get('flash_form_error', 'Form error. Please try again.'), 'danger')

    return redirect(url_for('assets.detail', id=id))


@assets_bp.route('/<int:id>/return', methods=['POST'])
@login_required
def return_asset(id):
    if not current_user.can_edit:
        abort(403)
    t = getattr(g, 't', {})
    asset = Asset.query.get_or_404(id)
    form = ReturnForm(prefix='ret')
    form.populate_choices()

    if form.validate_on_submit():
        to_site = Site.query.get(form.to_site_id.data) if form.to_site_id.data else None
        prev_site = asset.current_site
        asset.status = 'in_storage'
        asset.assigned_to_id = None
        if to_site:
            asset.current_site_id = to_site.id
        log_event(asset, 'returned', current_user,
                  from_site=prev_site,
                  to_site=to_site,
                  notes=(form.notes.data or '').strip() or None)
        db.session.commit()
        flash(t.get('flash_returned', '{sn} returned to storage.').format(sn=asset.serial_number), 'info')
    else:
        flash(t.get('flash_form_error', 'Form error. Please try again.'), 'danger')

    return redirect(url_for('assets.detail', id=id))


@assets_bp.route('/<int:id>/retire', methods=['POST'])
@login_required
def retire(id):
    if not current_user.can_edit:
        abort(403)
    t = getattr(g, 't', {})
    asset = Asset.query.get_or_404(id)
    asset.status = 'retired'
    asset.assigned_to_id = None
    log_event(asset, 'retired', current_user)
    db.session.commit()
    flash(t.get('flash_retired', '{sn} retired from service.').format(sn=asset.serial_number), 'secondary')
    return redirect(url_for('assets.detail', id=id))
