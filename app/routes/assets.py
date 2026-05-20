import json
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, g
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, TextAreaField, SubmitField, DecimalField, IntegerField
from wtforms.validators import DataRequired, Optional, Length, NumberRange
from collections import defaultdict

from app.models.asset import Asset, AssetType, AssetEvent
from app.models.site import Site
from app.models.user import User
from app.utils.events import log_event
from app.utils.translations import localize_form
from app.utils.mongo_helpers import get_or_404

assets_bp = Blueprint('assets', __name__, url_prefix='/assets')

CATEGORY_ORDER = [
    'Router', 'Aggregation', 'Access Switch', 'SFP', 'Cards',
    'Power Supply', 'Power Cords', 'Console Cables',
]
CATEGORY_LABELS = {
    'Router': 'Routers', 'Aggregation': 'Aggregation', 'Access Switch': 'Access Switches',
    'SFP': 'SFP Modules', 'Cards': 'Cards & Modules', 'Power Supply': 'Power Supplies',
    'Power Cords': 'Power Cords', 'Console Cables': 'Console Cables',
}


def _site_choices():
    return [('', '— None —')] + [(str(s.id), s.name) for s in Site.objects.order_by('name')]


def _user_choices():
    return [('', '— None —')] + [(str(u.id), u.name) for u in User.objects.order_by('name')]


def _type_choices():
    return [(str(t.id), f'{t.name} ({t.category})') for t in AssetType.objects.order_by('name')]


class AssetForm(FlaskForm):
    component_id  = StringField('Asset ID',       validators=[Optional(), Length(max=50)])
    serial_number = StringField('Mfr. Part No.',  validators=[DataRequired(), Length(max=100)])
    barcode       = StringField('Barcode',         validators=[Optional(), Length(max=100)])
    asset_type_id = SelectField('Asset Type', coerce=str, validators=[DataRequired()])
    model         = StringField('Description',     validators=[Optional(), Length(max=150)])
    manufacturer  = StringField('Manufacturer',    validators=[Optional(), Length(max=150)])
    notes         = TextAreaField('Notes',         validators=[Optional()])
    price_usd     = DecimalField('Price USD ($)',  validators=[Optional(), NumberRange(min=0)], places=0)
    price_nis     = DecimalField('Price NIS (₪)',  validators=[Optional(), NumberRange(min=0)], places=0)
    quantity      = IntegerField('Stock Qty',      validators=[Optional(), NumberRange(min=0)])
    min_threshold = IntegerField('Min Threshold',  validators=[Optional(), NumberRange(min=0)])
    submit        = SubmitField('Save Asset')

    def populate_choices(self):
        self.asset_type_id.choices = _type_choices()


class DismantleForm(FlaskForm):
    from_site_id = SelectField('Dismantled From', coerce=str, validators=[Optional()])
    notes        = TextAreaField('Notes', validators=[Optional()])
    submit       = SubmitField('Confirm Dismantle')

    def populate_choices(self):
        self.from_site_id.choices = _site_choices()


class AssignForm(FlaskForm):
    assigned_to_id = SelectField('Assign To',       coerce=str, validators=[DataRequired()])
    to_site_id     = SelectField('Deploy to Site',  coerce=str, validators=[Optional()])
    contact_id     = SelectField('Notify Contact',  coerce=str, validators=[Optional()])
    notes          = TextAreaField('Notes',         validators=[Optional()])
    submit         = SubmitField('Confirm Assignment')

    def populate_choices(self):
        from app.models.contact import Contact
        self.assigned_to_id.choices = [(str(u.id), u.name) for u in User.objects.order_by('name')]
        self.to_site_id.choices     = _site_choices()
        self.contact_id.choices     = [('', '— No notification —')] + [
            (str(c.id), f'{c.name}' + (f'  ✉ {c.email}' if c.email else '') + (f'  📱 {c.phone}' if c.phone else ''))
            for c in Contact.objects.order_by('name')
        ]


class MoveForm(FlaskForm):
    to_site_id = SelectField('Move to Site', coerce=str, validators=[DataRequired()])
    notes      = TextAreaField('Notes',      validators=[Optional()])
    submit     = SubmitField('Confirm Move')

    def populate_choices(self):
        self.to_site_id.choices = [(str(s.id), s.name) for s in Site.objects.order_by('name')]


class ReturnForm(FlaskForm):
    to_site_id = SelectField('Return to Site (Storage)', coerce=str, validators=[Optional()])
    notes      = TextAreaField('Notes', validators=[Optional()])
    submit     = SubmitField('Confirm Return')

    def populate_choices(self):
        self.to_site_id.choices = _site_choices()


class RetireForm(FlaskForm):
    submit = SubmitField('Retire Asset')


# ── List ─────────────────────────────────────────────────────────────────────

@assets_bp.route('/')
@login_required
def list_assets():
    q             = request.args.get('q', '').strip()
    status_filter = request.args.get('status', '')
    type_filter   = request.args.get('type', '')
    site_filter   = request.args.get('site', '')
    sort          = request.args.get('sort', 'created_at')
    order         = request.args.get('order', 'desc')

    qs = Asset.objects
    if q:
        import re
        pattern = re.compile(re.escape(q), re.IGNORECASE)
        qs = qs.filter(__raw__={
            '$or': [
                {'serial_number': {'$regex': pattern.pattern, '$options': 'i'}},
                {'model':         {'$regex': pattern.pattern, '$options': 'i'}},
                {'component_id':  {'$regex': pattern.pattern, '$options': 'i'}},
            ]
        })
    if status_filter:
        qs = qs(status=status_filter)
    if type_filter:
        at = AssetType.objects(id=type_filter).first()
        if at:
            qs = qs(asset_type=at)
    if site_filter:
        s = Site.objects(id=site_filter).first()
        if s:
            qs = qs(current_site=s)

    sort_map = {
        'component_id': 'component_id', 'serial_number': 'serial_number',
        'status': 'status', 'created_at': 'created_at',
        'price': 'price', 'price_nis': 'price_nis', 'price_usd': 'price_usd',
        'quantity': 'quantity',
    }
    sort_field = sort_map.get(sort, 'created_at')
    qs = qs.order_by(sort_field if order == 'asc' else f'-{sort_field}')

    assets = list(qs.select_related())

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

    all_types   = list(AssetType.objects)
    asset_types = sorted(all_types,
                         key=lambda t: CATEGORY_ORDER.index(t.name) if t.name in CATEGORY_ORDER else len(CATEGORY_ORDER))
    sites = list(Site.objects.order_by('name'))

    from app.models.settings import AppSetting
    global_settings = json.dumps(AppSetting.all_as_dict())

    # Commitments: sum of quantities in PENDING estimate items per asset
    from app.models.estimate import Estimate
    commitments = {}
    for est in Estimate.objects(status='pending').select_related():
        for item in est.items:
            if item.asset:
                aid = str(item.asset.id)
                commitments[aid] = commitments.get(aid, 0) + item.quantity

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
        existing = Asset.objects(serial_number=form.serial_number.data.strip().upper()).first()
        if existing:
            flash(
                t.get('flash_asset_duplicate', 'Model already registered: <a href="{url}">{sn}</a>').format(
                    url=url_for('assets.detail', id=str(existing.id)),
                    sn=existing.serial_number,
                ),
                'danger',
            )
            return redirect(url_for('assets.new_asset'))

        asset_type = AssetType.objects(id=form.asset_type_id.data).first()
        asset = Asset(
            component_id  = (form.component_id.data or '').strip() or None,
            serial_number = form.serial_number.data.strip().upper(),
            barcode       = (form.barcode.data or '').strip() or None,
            asset_type    = asset_type,
            model         = (form.model.data or '').strip() or None,
            manufacturer  = (form.manufacturer.data or '').strip() or None,
            status        = 'in_storage',
            notes         = (form.notes.data or '').strip() or None,
            price_usd     = float(form.price_usd.data) if form.price_usd.data is not None else None,
            price_nis     = float(form.price_nis.data) if form.price_nis.data is not None else None,
            quantity      = form.quantity.data,
            min_threshold = form.min_threshold.data,
        )
        asset.save()
        log_event(asset, 'created', current_user, notes=f'Asset registered. Status: {asset.status_label}')
        flash(t.get('flash_asset_created', '{sn} registered successfully.').format(sn=asset.serial_number), 'success')
        return redirect(url_for('assets.list_assets'))

    return render_template('assets/form.html', form=form, asset=None,
                           title=t.get('form_title_register_asset', 'Register New Asset'))


# ── Detail ───────────────────────────────────────────────────────────────────

@assets_bp.route('/<id>')
@login_required
def detail(id):
    t = getattr(g, 't', {})
    asset  = get_or_404(Asset, id)
    events = list(AssetEvent.objects(asset=asset).order_by('-event_date').select_related())

    dismantle_form = DismantleForm(prefix='dismantle')
    dismantle_form.populate_choices()
    if asset.current_site:
        dismantle_form.from_site_id.data = str(asset.current_site.id)
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
        asset=asset, events=events,
        dismantle_form=dismantle_form, assign_form=assign_form,
        move_form=move_form, return_form=return_form, retire_form=retire_form,
    )


# ── Edit ─────────────────────────────────────────────────────────────────────

@assets_bp.route('/<id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    if not current_user.can_edit:
        abort(403)
    t = getattr(g, 't', {})
    asset = get_or_404(Asset, id)
    form  = AssetForm()
    form.populate_choices()
    localize_form(form, t, submit_key='form_save_asset')

    if request.method == 'GET':
        form.component_id.data  = asset.component_id or ''
        form.serial_number.data = asset.serial_number
        form.barcode.data       = asset.barcode or ''
        form.asset_type_id.data = str(asset.asset_type.id) if asset.asset_type else ''
        form.model.data         = asset.model or ''
        form.manufacturer.data  = asset.manufacturer or ''
        form.notes.data         = asset.notes or ''
        form.price_usd.data     = asset.price_usd
        form.price_nis.data     = asset.price_nis
        form.quantity.data      = asset.quantity
        form.min_threshold.data = asset.min_threshold

    if form.validate_on_submit():
        asset.component_id  = (form.component_id.data or '').strip() or None
        asset.serial_number = form.serial_number.data.strip().upper()
        asset.barcode       = (form.barcode.data or '').strip() or None
        asset.asset_type    = AssetType.objects(id=form.asset_type_id.data).first()
        asset.model         = (form.model.data or '').strip() or None
        asset.manufacturer  = (form.manufacturer.data or '').strip() or None
        asset.notes         = (form.notes.data or '').strip() or None
        asset.price_usd     = float(form.price_usd.data) if form.price_usd.data is not None else None
        asset.price_nis     = float(form.price_nis.data) if form.price_nis.data is not None else None
        asset.quantity      = form.quantity.data
        asset.min_threshold = form.min_threshold.data
        asset.save()
        flash(t.get('flash_asset_updated', 'Asset updated successfully.'), 'success')
        return redirect(url_for('assets.list_assets'))

    return render_template('assets/form.html', form=form, asset=asset,
                           title=t.get('form_title_edit_asset', 'Edit Asset'))


# ── Actions ──────────────────────────────────────────────────────────────────

@assets_bp.route('/<id>/dismantle', methods=['POST'])
@login_required
def dismantle(id):
    if not current_user.can_edit:
        abort(403)
    t = getattr(g, 't', {})
    asset = get_or_404(Asset, id)
    form  = DismantleForm(prefix='dismantle')
    form.populate_choices()

    if form.validate_on_submit():
        from_site = Site.objects(id=form.from_site_id.data).first() if form.from_site_id.data else asset.current_site
        asset.status         = 'dismantled'
        asset.assignee       = None
        asset.current_site   = None
        asset.save()
        log_event(asset, 'dismantled', current_user, from_site=from_site,
                  notes=(form.notes.data or '').strip() or None)
        flash(t.get('flash_dismantled', '{sn} marked as dismantled.').format(sn=asset.serial_number), 'warning')
    else:
        flash(t.get('flash_form_error', 'Form error. Please try again.'), 'danger')

    return redirect(url_for('assets.detail', id=str(asset.id)))


@assets_bp.route('/<id>/assign', methods=['POST'])
@login_required
def assign(id):
    if not current_user.can_edit:
        abort(403)
    t = getattr(g, 't', {})
    asset = get_or_404(Asset, id)
    form  = AssignForm(prefix='assign')
    form.populate_choices()

    if form.validate_on_submit():
        to_site  = Site.objects(id=form.to_site_id.data).first() if form.to_site_id.data else None
        prev_site = asset.current_site
        assignee  = User.objects(id=form.assigned_to_id.data).first()
        asset.status       = 'assigned'
        asset.assignee     = assignee
        if to_site:
            asset.current_site = to_site
        asset.save()
        log_event(asset, 'assigned', current_user, from_site=prev_site, to_site=to_site,
                  notes=(form.notes.data or '').strip() or None)
        flash(t.get('flash_assigned', '{sn} assigned successfully.').format(sn=asset.serial_number), 'success')

        contact_id = form.contact_id.data
        if contact_id:
            from app.models.contact import Contact
            from app.utils.email_notify import send_assignment_email
            import os
            contact = Contact.objects(id=contact_id).first()
            if contact and contact.email:
                if not os.environ.get('SMTP_EMAIL'):
                    flash(
                        'Email not sent — SMTP is not configured. '
                        'Create a <strong>.env</strong> file next to Inventory.exe '
                        'with your SMTP credentials.',
                        'warning',
                    )
                else:
                    ok = send_assignment_email(
                        contact, asset,
                        assigned_to_name=assignee.name if assignee else 'N/A',
                        site_name=to_site.name if to_site else None,
                    )
                    if ok:
                        flash(f'Assignment email sent to {contact.email}.', 'info')
                    else:
                        flash(
                            f'Email to {contact.email} could not be delivered. '
                            'Check your SMTP credentials in the <strong>.env</strong> file.',
                            'warning',
                        )
    else:
        flash(t.get('flash_form_error', 'Form error. Please try again.'), 'danger')

    return redirect(url_for('assets.detail', id=str(asset.id)))


@assets_bp.route('/<id>/move', methods=['POST'])
@login_required
def move(id):
    if not current_user.can_edit:
        abort(403)
    t = getattr(g, 't', {})
    asset = get_or_404(Asset, id)
    form  = MoveForm(prefix='move')
    form.populate_choices()

    if form.validate_on_submit():
        to_site   = get_or_404(Site, form.to_site_id.data)
        prev_site = asset.current_site
        asset.current_site = to_site
        asset.save()
        log_event(asset, 'moved', current_user, from_site=prev_site, to_site=to_site,
                  notes=(form.notes.data or '').strip() or None)
        flash(t.get('flash_moved', '{sn} moved to {site}.').format(sn=asset.serial_number, site=to_site.name), 'success')
    else:
        flash(t.get('flash_form_error', 'Form error. Please try again.'), 'danger')

    return redirect(url_for('assets.detail', id=str(asset.id)))


@assets_bp.route('/<id>/return', methods=['POST'])
@login_required
def return_asset(id):
    if not current_user.can_edit:
        abort(403)
    t = getattr(g, 't', {})
    asset = get_or_404(Asset, id)
    form  = ReturnForm(prefix='ret')
    form.populate_choices()

    if form.validate_on_submit():
        to_site   = Site.objects(id=form.to_site_id.data).first() if form.to_site_id.data else None
        prev_site = asset.current_site
        asset.status   = 'in_storage'
        asset.assignee = None
        if to_site:
            asset.current_site = to_site
        asset.save()
        log_event(asset, 'returned', current_user, from_site=prev_site, to_site=to_site,
                  notes=(form.notes.data or '').strip() or None)
        flash(t.get('flash_returned', '{sn} returned to storage.').format(sn=asset.serial_number), 'info')
    else:
        flash(t.get('flash_form_error', 'Form error. Please try again.'), 'danger')

    return redirect(url_for('assets.detail', id=str(asset.id)))


@assets_bp.route('/<id>/retire', methods=['POST'])
@login_required
def retire(id):
    if not current_user.can_edit:
        abort(403)
    t = getattr(g, 't', {})
    asset = get_or_404(Asset, id)
    asset.status   = 'retired'
    asset.assignee = None
    asset.save()
    log_event(asset, 'retired', current_user)
    flash(t.get('flash_retired', '{sn} retired from service.').format(sn=asset.serial_number), 'secondary')
    return redirect(url_for('assets.detail', id=str(asset.id)))


@assets_bp.route('/<id>/delete', methods=['POST'])
@login_required
def delete(id):
    if not current_user.is_admin:
        abort(403)
    t = getattr(g, 't', {})
    asset = get_or_404(Asset, id)
    sn = asset.serial_number
    AssetEvent.objects(asset=asset).delete()
    asset.delete()
    flash(f'{sn} deleted.', 'danger')
    return redirect(url_for('assets.list_assets'))
