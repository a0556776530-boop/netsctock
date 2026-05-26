import csv
from io import StringIO
from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, flash, request, Response, abort, g
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email, Length, Optional

from app import bcrypt
from app.models.user import User
from app.models.asset import Asset, AssetEvent
from app.models.site import Site
from app.models.task import Task
from app.utils.translations import localize_form
from app.utils.mongo_helpers import get_or_404

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def _admin_required():
    if not current_user.is_admin:
        abort(403)


# ── Forms ─────────────────────────────────────────────────────────────────────

class NewUserForm(FlaskForm):
    name     = StringField('Full Name', validators=[DataRequired(), Length(max=100)])
    email    = StringField('Email',     validators=[DataRequired(), Email(check_deliverability=False)])
    role     = SelectField('Role', choices=[('technician','Technician'),('viewer','Viewer'),('admin','Admin')])
    password = PasswordField('Initial Password', validators=[DataRequired(), Length(min=8)])
    submit   = SubmitField('Create User')


class EditUserForm(FlaskForm):
    name         = StringField('Full Name', validators=[DataRequired(), Length(max=100)])
    role         = SelectField('Role', choices=[('technician','Technician'),('viewer','Viewer'),('admin','Admin')])
    new_password = PasswordField('New Password (leave blank to keep current)',
                                 validators=[Optional(), Length(min=8)])
    submit       = SubmitField('Save')


def _localize_user_form(form, t, is_new=True):
    localize_form(form, t,
                  submit_key='form_create_user' if is_new else 'form_save',
                  extra={'password': 'form_initial_password'} if is_new else
                        {'new_password': 'form_new_password_optional'})
    form.name.label.text = t.get('col_name', 'Name')

    role_choices = [
        ('technician', t.get('role_technician', 'Technician')),
        ('viewer',     t.get('role_viewer',     'Viewer')),
        ('admin',      t.get('role_admin',       'Admin')),
    ]
    form.role.choices = role_choices
    return form


# ── Users ─────────────────────────────────────────────────────────────────────

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
    _admin_required()
    t = getattr(g, 't', {})
    form = NewUserForm()
    _localize_user_form(form, t, is_new=True)
    if form.validate_on_submit():
        if User.objects(email=form.email.data.lower().strip()).first():
            flash(t.get('flash_user_exists', 'A user with this email already exists.'), 'danger')
        else:
            u = User(
                name=form.name.data.strip(),
                email=form.email.data.lower().strip(),
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
    _admin_required()
    t = getattr(g, 't', {})
    user = get_or_404(User, id)
    form = EditUserForm()
    _localize_user_form(form, t, is_new=False)

    if request.method == 'GET':
        form.name.data = user.name
        form.role.data = user.role

    if form.validate_on_submit():
        user.name = form.name.data.strip()
        user.role = form.role.data
        if form.new_password.data:
            user.password_hash = bcrypt.generate_password_hash(form.new_password.data).decode('utf-8')
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
    name = user.name
    Asset.objects(assignee=user).update(unset__assignee=1)
    user.delete()
    flash(t.get('flash_user_deleted', 'User {name} deleted.').format(name=name), 'warning')
    return redirect(url_for('admin.users'))


# ── Settings ─────────────────────────────────────────────────────────────────

@admin_bp.route('/settings', methods=['GET'])
@login_required
def settings():
    _admin_required()
    all_users = list(User.objects.order_by('name'))
    return render_template('admin/settings.html', users=all_users)


@admin_bp.route('/users/<id>/role', methods=['POST'])
@login_required
def update_role(id):
    _admin_required()
    from flask import jsonify
    user = get_or_404(User, id)
    if user.id == current_user.id:
        return jsonify(ok=False, error='Cannot change your own role'), 400
    new_role = (request.get_json(force=True) or {}).get('role', '')
    if new_role not in ('admin', 'technician', 'viewer'):
        return jsonify(ok=False, error='Invalid role'), 400
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
    sites       = list(Site.objects.order_by('name'))
    return render_template('admin/export.html',
                           asset_count=asset_count,
                           event_count=event_count,
                           task_count=task_count,
                           sites=sites)


@admin_bp.route('/export/assets.csv')
@login_required
def export_assets():
    _admin_required()
    headers = ['Asset ID','Serial Number','Barcode','Type','Category','Model','Manufacturer',
               'Status','Current Site','Assigned To','Notes','Created At']
    rows = []
    for a in Asset.objects.order_by('serial_number').select_related():
        rows.append([
            a.component_id or '',
            a.serial_number,
            a.barcode or '',
            a.asset_type.name if a.asset_type else '',
            a.asset_type.category if a.asset_type else '',
            a.model or '',
            a.manufacturer or '',
            a.status_label,
            a.current_site.name if a.current_site else '',
            a.assignee.name if a.assignee else '',
            (a.notes or '').replace('\n', ' '),
            a.created_at.strftime('%d/%m/%Y %H:%M') if a.created_at else '',
        ])
    return _csv_response(rows, headers, 'inventory_assets.csv')


@admin_bp.route('/export/events.csv')
@login_required
def export_events():
    _admin_required()
    headers = ['Event Date','Serial Number','Event Type','From Site','To Site','Performed By','Notes']
    rows = []
    for e in AssetEvent.objects.order_by('-event_date').select_related():
        rows.append([
            e.event_date.strftime('%d/%m/%Y %H:%M'),
            e.asset.serial_number if e.asset else '',
            e.event_label,
            e.from_site.name if e.from_site else '',
            e.to_site.name if e.to_site else '',
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


@admin_bp.route('/report/site/<id>.csv')
@login_required
def export_site_csv(id):
    _admin_required()
    site = get_or_404(Site, id)
    headers = ['Asset ID','Serial Number','Type','Model','Manufacturer','Status','Assigned To']
    rows = []
    for a in Asset.objects(current_site=site).order_by('serial_number').select_related():
        rows.append([
            a.component_id or '',
            a.serial_number,
            a.asset_type.name if a.asset_type else '',
            a.model or '',
            a.manufacturer or '',
            a.status_label,
            a.assignee.name if a.assignee else '',
        ])
    filename = f'inventory_site_{site.name.replace(" ","_")}.csv'
    return _csv_response(rows, headers, filename)


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
