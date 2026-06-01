import csv
from io import StringIO
from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, flash, request, Response, abort, g
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
    """Return True if any user (other than exclude_id) already has this password."""
    for u in User.objects():
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

def _role_choices(t):
    return [
        ('super_admin', t.get('role_super_admin', 'Super Admin')),
        ('admin',       t.get('role_admin',       'Admin')),
        ('viewer',      t.get('role_viewer',      'Viewer')),
        ('warehouse',   t.get('role_warehouse',   'Warehouse')),
    ]


def _localize_user_form(form, t, is_new=True):
    localize_form(form, t,
                  submit_key='form_create_user' if is_new else 'form_save',
                  extra={'password': 'form_initial_password'} if is_new else
                        {'new_password': 'form_new_password_optional'})
    form.name.label.text = t.get('col_name', 'Name')
    form.role.choices = _role_choices(t)
    return form


# ── Users (super_admin only) ──────────────────────────────────────────────────

@admin_bp.route('/users')
@login_required
def users():
    _admin_required()
    all_users = list(User.objects.order_by('name'))
    user_stats = {}
    for u in all_users:
        user_stats[u.id] = {
            'assets': Asset.objects(assignee=u).count(),
            'tasks':  Task.objects(assignee_name=u.name, status__in=['pending', 'in_progress']).count(),
        }
    return render_template('admin/users.html', users=all_users, user_stats=user_stats)


@admin_bp.route('/users/new', methods=['GET', 'POST'])
@login_required
def new_user():
    _super_admin_required()
    t = getattr(g, 't', {})
    form = NewUserForm()
    _localize_user_form(form, t, is_new=True)
    if form.validate_on_submit():
        if form.role.data not in VALID_ROLES:
            abort(400)
        if _password_already_used(form.password.data):
            flash(t.get('flash_same_password', 'New password must be different from your current password.'), 'danger')
            form.password.data = ''
            return render_template('admin/new_user.html', form=form)
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

    # Regular admin can only edit their own account (password only)
    if not current_user.is_super_admin:
        if user.id != current_user.id:
            abort(403)
        # Show password-only form
        form = ChangeOwnPasswordForm()
        if form.validate_on_submit():
            if not bcrypt.check_password_hash(user.password_hash, form.current_password.data):
                flash(t.get('flash_wrong_password', 'Current password is incorrect.'), 'danger')
                form.new_password.data = ''
            elif bcrypt.check_password_hash(user.password_hash, form.new_password.data):
                flash(t.get('flash_same_password', 'New password must be different from your current password.'), 'danger')
                form.new_password.data = ''
            elif _password_already_used(form.new_password.data, exclude_id=user.id):
                flash(t.get('flash_password_taken', 'הסיסמה קיימת במערכת — בחר סיסמה אחרת.'), 'danger')
                form.new_password.data = ''
            else:
                user.password_hash = bcrypt.generate_password_hash(form.new_password.data).decode('utf-8')
                user.save()
                flash(t.get('flash_user_updated', '{name} updated successfully.').format(name=user.name), 'success')
                return redirect(url_for('main.dashboard'))
        return render_template('admin/change_password.html', form=form, user=user)

    # Super admin: full edit
    form = EditUserForm()
    _localize_user_form(form, t, is_new=False)

    if request.method == 'GET':
        form.name.data = user.name
        form.role.data = user.role

    if form.validate_on_submit():
        if form.new_password.data:
            if not form.current_password.data or not bcrypt.check_password_hash(user.password_hash, form.current_password.data):
                flash(t.get('flash_wrong_password', 'Current password is incorrect.'), 'danger')
                form.new_password.data = ''
                return render_template('admin/edit_user.html', form=form, user=user)
            if bcrypt.check_password_hash(user.password_hash, form.new_password.data):
                flash(t.get('flash_same_password', 'New password must be different from your current password.'), 'danger')
                form.new_password.data = ''
                return render_template('admin/edit_user.html', form=form, user=user)
            if _password_already_used(form.new_password.data, exclude_id=user.id):
                flash(t.get('flash_password_taken', 'הסיסמה קיימת במערכת — בחר סיסמה אחרת.'), 'danger')
                form.new_password.data = ''
                return render_template('admin/edit_user.html', form=form, user=user)
            user.password_hash = bcrypt.generate_password_hash(form.new_password.data).decode('utf-8')

        # Prevent removing the last super_admin
        if user.role == 'super_admin' and form.role.data != 'super_admin':
            if User.objects(role='super_admin').count() <= 1:
                flash(t.get('flash_last_super_admin', 'Cannot change — this is the last Super Admin.'), 'danger')
                return render_template('admin/edit_user.html', form=form, user=user)

        user.name = form.name.data.strip()
        user.role = form.role.data
        user.save()
        flash(t.get('flash_user_updated', '{name} updated successfully.').format(name=user.name), 'success')
        return redirect(url_for('admin.users'))
    return render_template('admin/edit_user.html', form=form, user=user)


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
        user.save()
        flash(t.get('flash_password_reset', 'Password for {name} has been reset.').format(name=user.name), 'success')
        return redirect(url_for('admin.users'))
    return render_template('admin/reset_password.html', form=form, user=user)


# ── Settings ─────────────────────────────────────────────────────────────────

@admin_bp.route('/settings', methods=['GET'])
@login_required
def settings():
    _super_admin_required()
    all_users = list(User.objects.order_by('name'))
    return render_template('admin/settings.html', users=all_users)


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


# ── Export ────────────────────────────────────────────────────────────────────

@admin_bp.route('/export')
@login_required
def export():
    _admin_required()
    asset_count = Asset.objects.count()
    event_count = AssetEvent.objects.count()
    task_count  = Task.objects.count()
    return render_template('admin/export.html',
                           asset_count=asset_count,
                           event_count=event_count,
                           task_count=task_count)


@admin_bp.route('/export/assets.csv')
@login_required
def export_assets():
    _admin_required()
    headers = ['מקט רכיב', 'מקט יצרן', 'כמות במחסן']
    rows = []
    for a in Asset.objects.order_by('serial_number'):
        rows.append([
            a.component_id or '',
            a.serial_number or '',
            a.quantity if a.quantity is not None else '',
        ])
    return _csv_response(rows, headers, 'inventory_assets.csv')


@admin_bp.route('/export/events.csv')
@login_required
def export_events():
    _admin_required()
    headers = ['Event Date','Serial Number','Event Type','Performed By','Notes']
    rows = []
    for e in AssetEvent.objects.order_by('-event_date').select_related():
        rows.append([
            e.event_date.strftime('%d/%m/%Y %H:%M'),
            e.asset.serial_number if e.asset else '',
            e.event_label,
            e.performed_by_user.name if e.performed_by_user else '',
            (e.notes or '').replace('\n', ' '),
        ])
    return _csv_response(rows, headers, 'inventory_events.csv')


@admin_bp.route('/export/tasks.csv')
@login_required
def export_tasks():
    _admin_required()
    headers = ['Title', 'Status', 'Assigned To', 'Notes', 'Created At']
    rows = []
    for t in Task.objects.order_by('-created_at'):
        rows.append([
            t.title,
            t.status_label,
            t.assignee_name or '',
            (t.notes or '').replace('\n', ' '),
            t.created_at.strftime('%d/%m/%Y %H:%M') if t.created_at else '',
        ])
    return _csv_response(rows, headers, 'inventory_tasks.csv')


def _csv_response(rows, headers, filename):
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(headers)
    writer.writerows(rows)
    output = '﻿' + si.getvalue()
    return Response(
        output,
        mimetype='text/csv; charset=utf-8-sig',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )
