import csv
from io import StringIO
from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, flash, request, Response, abort
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email, Length, Optional

from app import db, bcrypt
from app.models.user import User
from app.models.asset import Asset, AssetEvent
from app.models.site import Site
from app.models.task import Task

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def _admin_required():
    if not current_user.is_admin:
        abort(403)


# ── Forms ─────────────────────────────────────────────────────────────────────

class NewUserForm(FlaskForm):
    name     = StringField('שם מלא',  validators=[DataRequired(), Length(max=100)])
    email    = StringField('אימייל',      validators=[DataRequired(), Email(check_deliverability=False)])
    role     = SelectField('תפקיד', choices=[('technician','טכנאי'),('viewer','צופה'),('admin','מנהל')])
    password = PasswordField('סיסמה ראשונית', validators=[DataRequired(), Length(min=8)])
    submit   = SubmitField('צור משתמש')


class EditUserForm(FlaskForm):
    name  = StringField('שם מלא', validators=[DataRequired(), Length(max=100)])
    role  = SelectField('תפקיד', choices=[('technician','טכנאי'),('viewer','צופה'),('admin','מנהל')])
    new_password = PasswordField('סיסמה חדשה (השאר ריק לשמירת הנוכחית)',
                                 validators=[Optional(), Length(min=8)])
    submit = SubmitField('שמור')


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
    form = NewUserForm()
    if form.validate_on_submit():
        if User.query.filter_by(email=form.email.data.lower().strip()).first():
            flash('משתמש עם אימייל זה כבר קיים.', 'danger')
        else:
            u = User(
                name=form.name.data.strip(),
                email=form.email.data.lower().strip(),
                password_hash=bcrypt.generate_password_hash(form.password.data).decode('utf-8'),
                role=form.role.data,
            )
            db.session.add(u)
            db.session.commit()
            flash(f'המשתמש {u.name} נוצר בהצלחה.', 'success')
            return redirect(url_for('admin.users'))
    return render_template('admin/new_user.html', form=form)


@admin_bp.route('/users/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_user(id):
    _admin_required()
    user = User.query.get_or_404(id)
    form = EditUserForm(obj=user)
    if form.validate_on_submit():
        user.name = form.name.data.strip()
        user.role = form.role.data
        if form.new_password.data:
            user.password_hash = bcrypt.generate_password_hash(form.new_password.data).decode('utf-8')
        db.session.commit()
        flash(f'{user.name} עודכן בהצלחה.', 'success')
        return redirect(url_for('admin.users'))
    return render_template('admin/edit_user.html', form=form, user=user)


@admin_bp.route('/users/<int:id>/delete', methods=['POST'])
@login_required
def delete_user(id):
    _admin_required()
    user = User.query.get_or_404(id)
    if user.id == current_user.id:
        flash('לא ניתן למחוק את החשבון שלך.', 'danger')
        return redirect(url_for('admin.users'))
    name = user.name
    # Unlink references before deleting
    Asset.query.filter_by(assigned_to_id=user.id).update({'assigned_to_id': None})
    Task.query.filter_by(assigned_to_id=user.id).update({'assigned_to_id': None})
    db.session.delete(user)
    db.session.commit()
    flash(f'המשתמש {name} נמחק.', 'warning')
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
    headers = ['Serial Number','Barcode','Type','Category','Model','Manufacturer',
               'Status','Current Site','Assigned To','Due Date','Notes','Created At']
    rows = []
    for a in Asset.query.order_by(Asset.serial_number).all():
        rows.append([
            a.serial_number,
            a.barcode or '',
            a.asset_type.name if a.asset_type else '',
            a.asset_type.category if a.asset_type else '',
            a.model or '',
            a.manufacturer or '',
            a.status_label,
            a.current_site.name if a.current_site else '',
            a.assignee.name if a.assignee else '',
            a.due_date.strftime('%d/%m/%Y') if a.due_date else '',
            (a.notes or '').replace('\n', ' '),
            a.created_at.strftime('%d/%m/%Y %H:%M') if a.created_at else '',
        ])
    return _csv_response(rows, headers, 'netstock_assets.csv')


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
    return _csv_response(rows, headers, 'netstock_events.csv')


@admin_bp.route('/export/tasks.csv')
@login_required
def export_tasks():
    _admin_required()
    headers = ['Title','Status','Due Date','Assigned To','Related Asset','Notes','Created At']
    rows = []
    for t in Task.query.order_by(Task.due_date).all():
        rows.append([
            t.title,
            t.status_label,
            t.due_date.strftime('%d/%m/%Y') if t.due_date else '',
            t.assignee.name if t.assignee else '',
            t.asset.serial_number if t.asset else '',
            (t.notes or '').replace('\n', ' '),
            t.created_at.strftime('%d/%m/%Y %H:%M') if t.created_at else '',
        ])
    return _csv_response(rows, headers, 'netstock_tasks.csv')


# ── Site report ────────────────────────────────────────────────────────────────

@admin_bp.route('/report/site/<int:id>.csv')
@login_required
def export_site_csv(id):
    _admin_required()
    site = Site.query.get_or_404(id)
    headers = ['Serial Number','Type','Model','Manufacturer','Status','Assigned To','Due Date']
    rows = []
    for a in Asset.query.filter_by(current_site_id=id).order_by(Asset.serial_number).all():
        rows.append([
            a.serial_number,
            a.asset_type.name if a.asset_type else '',
            a.model or '',
            a.manufacturer or '',
            a.status_label,
            a.assignee.name if a.assignee else '',
            a.due_date.strftime('%d/%m/%Y') if a.due_date else '',
        ])
    filename = f'netstock_site_{site.name.replace(" ","_")}.csv'
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
