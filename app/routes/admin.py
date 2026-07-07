from datetime import datetime
from flask import make_response

from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, g
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Length, Optional

from app import bcrypt
from app.models.user import User
from app.models.asset import Asset, AssetEvent
from app.models.task import Task
from app.utils.translations import localize_form


def _password_already_used(plaintext, exclude_id=None):
    """Return True if any user (other than exclude_id) already has this password.
    Sorted by last_login so recently-active users are checked first — exits early on match.
    """
    qs = User.objects.order_by('-last_login').only('id', 'password_hash')
    for u in qs:
        if exclude_id and str(u.id) == str(exclude_id):
            continue
        if bcrypt.check_password_hash(u.password_hash, plaintext):
            return True
    return False
from app.utils.mongo_helpers import get_or_404

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def _admin_required():
    if not current_user.is_admin:
        abort(403)


def _super_admin_required():
    if not current_user.is_super_admin:
        abort(403)


# ── Forms ─────────────────────────────────────────────────────────────────────

class NewUserForm(FlaskForm):
    name     = StringField('Name', validators=[DataRequired(), Length(max=100)])
    role     = SelectField('Role', choices=[])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    submit   = SubmitField('Create User')


class EditUserForm(FlaskForm):
    name             = StringField('Name',             validators=[DataRequired(), Length(max=100)])
    role             = SelectField('Role',             choices=[])
    current_password = PasswordField('Current Password', validators=[Optional()])
    new_password     = PasswordField('New Password',     validators=[Optional(), Length(min=8)])
    submit           = SubmitField('Save')


class ChangeOwnPasswordForm(FlaskForm):
    current_password = PasswordField('Current Password', validators=[DataRequired()])
    new_password     = PasswordField('New Password',     validators=[DataRequired(), Length(min=8)])
    submit           = SubmitField('Save')


class ResetPasswordForm(FlaskForm):
    new_password = PasswordField('New Password', validators=[DataRequired(), Length(min=8)])
    submit       = SubmitField('Reset Password')


VALID_ROLES = ('super_admin', 'admin', 'viewer', 'warehouse')

def _role_choices(t, include_super=True):
    choices = []
    if include_super:
        choices.append(('super_admin', t.get('role_super_admin', 'Super Admin')))
    choices += [
        ('admin',     t.get('role_admin',     'Admin')),
        ('viewer',    t.get('role_viewer',    'Viewer')),
        ('warehouse', t.get('role_warehouse', 'Warehouse')),
    ]
    return choices

# Roles an admin (non-super) is allowed to assign
_ADMIN_ASSIGNABLE_ROLES = {'admin', 'viewer', 'warehouse'}


def _localize_user_form(form, t, is_new=True):
    localize_form(form, t,
                  submit_key='form_create_user' if is_new else 'form_save',
                  extra={'password': 'form_initial_password'} if is_new else
                        {'new_password': 'form_new_password_optional'})
    form.name.label.text = t.get('col_name', 'Name')
    if not form.role.choices:
        form.role.choices = _role_choices(t, include_super=current_user.is_super_admin)
    return form


# ── Users (super_admin only) ──────────────────────────────────────────────────

@admin_bp.route('/users')
@login_required
def users():
    _admin_required()
    all_users = list(User.objects.order_by('name'))

    # Two aggregations instead of N×2 individual count queries
    asset_counts = {
        str(r['_id']): r['count']
        for r in Asset._get_collection().aggregate([
            {'$match': {'assigned_to_id': {'$exists': True, '$ne': None}}},
            {'$group': {'_id': '$assigned_to_id', 'count': {'$sum': 1}}},
        ])
    }
    task_counts = {
        r['_id']: r['count']
        for r in Task._get_collection().aggregate([
            {'$match': {'status': {'$in': ['pending', 'in_progress']}}},
            {'$group': {'_id': '$assignee_name', 'count': {'$sum': 1}}},
        ])
    }
    user_stats = {
        u.id: {
            'assets': asset_counts.get(str(u.id), 0),
            'tasks':  task_counts.get(u.name, 0),
        }
        for u in all_users
    }
    return render_template('admin/users.html', users=all_users, user_stats=user_stats)


@admin_bp.route('/users/new', methods=['GET', 'POST'])
@login_required
def new_user():
    _admin_required()
    t = getattr(g, 't', {})
    form = NewUserForm()
    include_super = current_user.is_super_admin
    form.role.choices = _role_choices(t, include_super=include_super)
    _localize_user_form(form, t, is_new=True)
    if form.validate_on_submit():
        # Admin (non-super) can only assign allowed roles
        if not current_user.is_super_admin and form.role.data not in _ADMIN_ASSIGNABLE_ROLES:
            abort(403)
        if form.role.data not in VALID_ROLES:
            abort(400)
        if _password_already_used(form.password.data):
            flash(t.get('flash_password_taken', 'הסיסמה קיימת במערכת — בחר סיסמה אחרת.'), 'danger')
            return redirect(url_for('admin.new_user'), 303)
        u = User(
            name=form.name.data.strip(),
            password_hash=bcrypt.generate_password_hash(form.password.data).decode('utf-8'),
            role=form.role.data,
        )
        u.save()
        flash(t.get('flash_user_created', 'User {name} created successfully.').format(name=u.name), 'success')
        return redirect(url_for('admin.users'))
    return render_template('admin/new_user.html', form=form)


@admin_bp.route('/users/<id>/edit', methods=['GET', 'POST'])
@login_required
def edit_user(id):
    t = getattr(g, 't', {})
    user = get_or_404(User, id)

    # Non-super admin: can edit name+role of non-super users, or own password
    if not current_user.is_super_admin:
        # Cannot edit super_admin accounts
        if user.is_super_admin:
            abort(403)
        # Editing own account — password only
        if user.id == current_user.id:
            form = ChangeOwnPasswordForm()
            if form.validate_on_submit():
                if not bcrypt.check_password_hash(user.password_hash, form.current_password.data):
                    flash(t.get('flash_wrong_password', 'Current password is incorrect.'), 'danger')
                elif bcrypt.check_password_hash(user.password_hash, form.new_password.data):
                    flash(t.get('flash_same_password', 'New password must be different from your current password.'), 'danger')
                elif _password_already_used(form.new_password.data, exclude_id=user.id):
                    flash(t.get('flash_password_taken', 'הסיסמה קיימת במערכת — בחר סיסמה אחרת.'), 'danger')
                else:
                    user.password_hash = bcrypt.generate_password_hash(form.new_password.data).decode('utf-8')
                    user.save()
                    flash(t.get('flash_user_updated', '{name} updated successfully.').format(name=user.name), 'success')
                    return redirect(url_for('main.dashboard'), 303)
            return redirect(url_for('admin.edit_user', id=str(user.id)), 303)
        # Editing another user (non-super) — name + role only, no password
        form = EditUserForm()
        form.role.choices = _role_choices(t, include_super=False)
        localize_form(form, t, submit_key='form_save')
        form.name.label.text = t.get('col_name', 'Name')
        if request.method == 'GET':
            form.name.data = user.name
            form.role.data = user.role
        if form.validate_on_submit():
            if form.role.data not in _ADMIN_ASSIGNABLE_ROLES:
                abort(403)
            user.name = form.name.data.strip()
            user.role = form.role.data
            user.save()
            flash(t.get('flash_user_updated', '{name} updated successfully.').format(name=user.name), 'success')
            return redirect(url_for('admin.users'))
        return render_template('admin/edit_user.html', form=form, user=user)

    # Super admin: full edit
    form = EditUserForm()
    _localize_user_form(form, t, is_new=False)

    if request.method == 'GET':
        form.name.data = user.name
        form.role.data = user.role

    if form.validate_on_submit():
        if form.new_password.data:
            editing_self = (str(user.id) == str(current_user.id))
            # When editing own account, verify current password; for other users no need
            if editing_self:
                if not form.current_password.data or not bcrypt.check_password_hash(user.password_hash, form.current_password.data):
                    flash(t.get('flash_wrong_password', 'Current password is incorrect.'), 'danger')
                    return redirect(url_for('admin.edit_user', id=str(user.id)), 303)
            if bcrypt.check_password_hash(user.password_hash, form.new_password.data):
                flash(t.get('flash_same_password', 'New password must be different from your current password.'), 'danger')
                return redirect(url_for('admin.edit_user', id=str(user.id)), 303)
            if _password_already_used(form.new_password.data, exclude_id=user.id):
                flash(t.get('flash_password_taken', 'הסיסמה קיימת במערכת — בחר סיסמה אחרת.'), 'danger')
                return redirect(url_for('admin.edit_user', id=str(user.id)), 303)
            user.password_hash = bcrypt.generate_password_hash(form.new_password.data).decode('utf-8')
            user.session_version = (user.session_version or 0) + 1

        # Prevent removing the last super_admin
        if user.role == 'super_admin' and form.role.data != 'super_admin':
            if User.objects(role='super_admin').count() <= 1:
                flash(t.get('flash_last_super_admin', 'Cannot change — this is the last Super Admin.'), 'danger')
                return redirect(url_for('admin.edit_user', id=str(user.id)), 303)

        user.name = form.name.data.strip()
        user.role = form.role.data

        # Profile photo — base64 data URI sent from JS
        photo_data = request.form.get('profile_photo_data', '').strip()
        if photo_data == 'REMOVE':
            user.profile_photo = None
        elif photo_data:
            user.profile_photo = photo_data

        user.save()

        # Bust all conversation caches so photo update is visible in chat
        if photo_data:
            from app.utils.cache import cache as _cache
            from app.models.user import _user_cache
            _user_cache.pop(str(user.id), None)
            for uid in list(_user_cache.keys()):
                _cache.delete(f'chat_convs_{uid}')
            _cache.delete(f'chat_convs_{user.id}')

        flash(t.get('flash_user_updated', '{name} updated successfully.').format(name=user.name), 'success')
        return redirect(url_for('admin.users'))
    editing_self = (str(user.id) == str(current_user.id))
    return render_template('admin/edit_user.html', form=form, user=user, editing_self=editing_self)


@admin_bp.route('/users/<id>/delete', methods=['POST'])
@login_required
def delete_user(id):
    _admin_required()
    t = getattr(g, 't', {})
    user = get_or_404(User, id)

    if user.id == current_user.id:
        flash(t.get('flash_cannot_delete_self', 'You cannot delete your own account.'), 'danger')
        return redirect(url_for('admin.users'))

    # Regular admin can only delete viewers
    if not current_user.is_super_admin:
        if user.role not in ('viewer',):
            abort(403)

    # Protect last super admin
    if user.is_super_admin and User.objects(role='super_admin').count() <= 1:
        flash(t.get('flash_last_super_admin', 'Cannot delete — this is the last Super Admin.'), 'danger')
        return redirect(url_for('admin.users'))

    name = user.name
    Asset.objects(assignee=user).update(unset__assignee=1)
    user.delete()
    flash(t.get('flash_user_deleted', 'User {name} deleted.').format(name=name), 'warning')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<id>/reset-password', methods=['GET', 'POST'])
@login_required
def reset_password(id):
    _super_admin_required()
    t = getattr(g, 't', {})
    user = get_or_404(User, id)
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.password_hash = bcrypt.generate_password_hash(form.new_password.data).decode('utf-8')
        user.session_version = (user.session_version or 0) + 1
        user.save()
        flash(t.get('flash_password_reset', 'Password for {name} has been reset.').format(name=user.name), 'success')
        return redirect(url_for('admin.users'))
    return render_template('admin/reset_password.html', form=form, user=user)


# ── Settings ─────────────────────────────────────────────────────────────────

@admin_bp.route('/settings', methods=['GET'])
@login_required
def settings():
    _super_admin_required()
    from app.models.settings import AppSetting
    all_users = list(User.objects.order_by('name'))
    alloc_counter = int(AppSetting.get('alloc_counter') or 0)
    return render_template('admin/settings.html', users=all_users,
                           alloc_counter=alloc_counter)


@admin_bp.route('/settings/alloc-counter', methods=['POST'])
@login_required
def set_alloc_counter():
    _super_admin_required()
    from app.models.settings import AppSetting
    val = request.form.get('alloc_counter', '').strip()
    if val.isdigit() and int(val) > 0:
        AppSetting.set('alloc_counter', int(val))
        flash(f'Counter הקצאות עודכן ל-{val}. ההצעה הבאה תהיה {int(val)+1}.', 'success')
    else:
        flash('ערך לא תקין.', 'danger')
    return redirect(url_for('admin.settings'))


@admin_bp.route('/users/<id>/role', methods=['POST'])
@login_required
def update_role(id):
    _super_admin_required()
    from flask import jsonify
    user = get_or_404(User, id)
    if user.id == current_user.id:
        return jsonify(ok=False, error='Cannot change your own role'), 400
    new_role = (request.get_json(force=True) or {}).get('role', '')
    if new_role not in VALID_ROLES:
        return jsonify(ok=False, error='Invalid role'), 400
    if user.role == 'super_admin' and new_role != 'super_admin':
        if User.objects(role='super_admin').count() <= 1:
            return jsonify(ok=False, error='Cannot demote the last Super Admin'), 400
    user.role = new_role
    user.save()
    return jsonify(ok=True)


# ── Login History ─────────────────────────────────────────────────────────────

@admin_bp.route('/login-history')
@login_required
def login_history():
    _admin_required()
    from mongoengine.connection import get_db

    col = get_db('default')['login_events']

    page           = max(1, request.args.get('page', 1, type=int))
    per_page       = 50
    user_filter    = request.args.get('user', '').strip()
    success_filter = request.args.get('success', '')
    date_from      = request.args.get('date_from', '')
    date_to        = request.args.get('date_to', '')

    filt = {}
    if user_filter:
        import re as _re
        filt['user_name'] = {'$regex': _re.escape(user_filter), '$options': 'i'}
    if success_filter == '1':
        filt['success'] = True
    elif success_filter == '0':
        filt['success'] = False
    if date_from:
        try:
            filt.setdefault('timestamp', {})['$gte'] = datetime.strptime(date_from, '%Y-%m-%d')
        except ValueError:
            pass
    if date_to:
        try:
            filt.setdefault('timestamp', {})['$lte'] = datetime.strptime(date_to + ' 23:59:59', '%Y-%m-%d %H:%M:%S')
        except ValueError:
            pass

    total  = col.count_documents(filt)
    events = list(col.find(filt).sort([('_id', -1)]).skip((page - 1) * per_page).limit(per_page))
    pages  = max(1, (total + per_page - 1) // per_page)

    resp = make_response(render_template(
        'admin/login_history.html',
        events=events,
        total=total,
        page=page,
        pages=pages,
        per_page=per_page,
        user_filter=user_filter,
        success_filter=success_filter,
        date_from=date_from,
        date_to=date_to,
    ))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    return resp


