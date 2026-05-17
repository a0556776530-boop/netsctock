import csv
from io import StringIO
from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, flash, request, Response, abort, g
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email, Length, Optional

from app import db, bcrypt
from app.models.user import User
from app.models.asset import Asset, AssetEvent
from app.models.site import Site
from app.models.task import Task
from app.utils.translations import localize_form

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def _admin_required():
    if not current_user.is_admin:
        abort(403)


# ── Forms ─────────────────────────────────────────────────────────────────────

class NewUserForm(FlaskForm):
    name     = StringField('Full Name',  validators=[DataRequired(), Length(max=100)])
    email    = StringField('Email',      validators=[DataRequired(), Email(check_deliverability=False)])
    role     = SelectField('Role', choices=[('technician','Technician'),('viewer','Viewer'),('admin','Admin')])
    password = PasswordField('Initial Password', validators=[DataRequired(), Length(min=8)])
    submit   = SubmitField('Create User')


class EditUserForm(FlaskForm):
    name  = StringField('Full Name', validators=[DataRequired(), Length(max=100)])
    role  = SelectField('Role', choices=[('technician','Technician'),('viewer','Viewer'),('admin','Admin')])
    new_password = PasswordField('New Password (leave blank to keep current)',
                                 validators=[Optional(), Length(min=8)])
    submit = SubmitField('Save')


def _localize_user_form(form, t, is_new=True):
    localize_form(form, t,
                  submit_key='form_create_user' if is_new else 'form_save',
                  extra={'password': 'form_initial_password'} if is_new else
                        {'new_password': 'form_new_password_optional'})
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
    all_users = User.query.order_by(User.name).all()
    user_stats = {}
    for u in all_users:
        user_stats[u.id] = {
            'assets': Asset.query.filter_by(assigned_to_id=u.id).count(),
            'tasks':  Task.query.filter_by(assigned_to_id=u.id, status='pending').count(),
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
        if User.query.filter_by(email=form.email.data.lower().strip()).first():
            flash(t.get('flash_user_exists', 'A user with this email already exists.'), 'danger')
        else:
            u = User(
                name=form.name.data.strip(),
                email=form.email.data.lower().strip(),
                password_hash=bcrypt.generate_password_hash(form.password.data).decode('utf-8'),
                role=form.role.data,
            )
            db.session.add(u)
            db.session.commit()
            flash(t.get('flash_user_created', 'User {name} created successfully.').format(name=u.name), 'success')
            return redirect(url_for('admin.users'))
    return render_template('admin/new_user.html', form=form)


@admin_bp.route('/users/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_user(id):
    _admin_required()
    t = getattr(g, 't', {})
    user = User.query.get_or_404(id)
    form = EditUserForm(obj=user)
    _localize_user_form(form, t, is_new=False)
    if form.validate_on_submit():
        user.name = form.name.data.strip()
        user.role = form.role.data
        if form.new_password.data:
            user.password_hash = bcrypt.generate_password_hash(form.new_password.data).decode('utf-8')
        db.session.commit()
        flash(t.get('flash_user_updated', '{name} updated successfully.').format(name=user.name), 'success')
        return redirect(url_for('admin.users'))
    return render_template('admin/edit_user.html', form=form, user=user)


@admin_bp.route('/users/<int:id>/delete', methods=['POST'])
@login_required
def delete_user(id):
    _admin_required()
    t = getattr(g, 't', {})
    user = User.query.get_or_404(id)
    if user.id == current_user.id:
        flash(t.get('flash_cannot_delete_self', 'You cannot delete your own account.'), 'danger')
        return redirect(url_for('admin.users'))
    name = user.name
    Asset.query.filter_by(assigned_to_id=user.id).update({'assigned_to_id': None})
    Task.query.filter_by(assigned_to_id=user.id).update({'assigned_to_id': None})
    db.session.delete(user)
    db.session.commit()
    flash(t.get('flash_user_deleted', 'User {name} deleted.').format(name=name), 'warning')
    return redirect(url_for('admin.users'))


# ── Export ────────────────────────────────────────────────────────────────────

@admin_bp.route('/export')
@login_required
def export():
    _admin_required()
    asset_count = Asset.query.count()
    event_count = AssetEvent.query.count()
    task_count  = Task.query.count()
    sites       = Site.query.order_by(Site.name).all()
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
    for a in Asset.query.order_by(Asset.serial_number).all():
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
    headers = ['Event Date','Serial Number','Event Type','From Site','To Site',
               'Performed By','Notes']
    rows = []
    events = (AssetEvent.query
              .order_by(AssetEvent.event_date.desc())
              .all())
    for e in events:
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
    headers = ['Title','Status','Assigned To','Related Asset','Notes','Created At']
    rows = []
    for t in Task.query.order_by(Task.created_at.desc()).all():
        rows.append([
            t.title,
            t.status_label,
            t.assignee.name if t.assignee else '',
            t.asset.serial_number if t.asset else '',
            (t.notes or '').replace('\n', ' '),
            t.created_at.strftime('%d/%m/%Y %H:%M') if t.created_at else '',
        ])
    return _csv_response(rows, headers, 'inventory_tasks.csv')


# ── Site report ────────────────────────────────────────────────────────────────

@admin_bp.route('/report/site/<int:id>.csv')
@login_required
def export_site_csv(id):
    _admin_required()
    site = Site.query.get_or_404(id)
    headers = ['Asset ID','Serial Number','Type','Model','Manufacturer','Status','Assigned To']
    rows = []
    for a in Asset.query.filter_by(current_site_id=id).order_by(Asset.serial_number).all():
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


# ── Helper ────────────────────────────────────────────────────────────────────

def _csv_response(rows, headers, filename):
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(headers)
    writer.writerows(rows)
    output = '﻿' + si.getvalue()   # UTF-8 BOM so Excel opens correctly
    return Response(
        output,
        mimetype='text/csv; charset=utf-8-sig',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )
