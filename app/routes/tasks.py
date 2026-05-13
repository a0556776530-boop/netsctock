from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, TextAreaField, DateField, SubmitField
from wtforms.validators import DataRequired, Optional, Length
from datetime import date, timedelta

from app import db
from app.models.task import Task
from app.models.asset import Asset
from app.models.user import User

tasks_bp = Blueprint('tasks', __name__, url_prefix='/tasks')


# ── Form ─────────────────────────────────────────────────────────────────────

def _asset_choices():
    assets = Asset.query.order_by(Asset.serial_number).all()
    return [(0, '— None —')] + [(a.id, f'{a.serial_number}  ({a.asset_type.name if a.asset_type else "?"})') for a in assets]


def _user_choices(include_none=True):
    users = User.query.order_by(User.name).all()
    base = [(0, '— None —')] if include_none else []
    return base + [(u.id, u.name) for u in users]


class TaskForm(FlaskForm):
    title = StringField('כותרת המשימה', validators=[DataRequired(), Length(max=255)])
    asset_id = SelectField('ציוד קשור', coerce=int, validators=[Optional()])
    assigned_to_id = SelectField('מוקצה ל', coerce=int, validators=[Optional()])
    due_date = DateField('תאריך יעד', validators=[Optional()])
    status = SelectField('סטטוס', choices=[
        ('pending', 'ממתין'),
        ('in_progress', 'בביצוע'),
        ('done', 'הושלם'),
    ])
    notes = TextAreaField('הערות', validators=[Optional()])
    submit = SubmitField('שמור משימה')

    def populate_choices(self):
        self.asset_id.choices = _asset_choices()
        self.assigned_to_id.choices = _user_choices()


# ── List ─────────────────────────────────────────────────────────────────────

@tasks_bp.route('/')
@login_required
def list_tasks():
    status_filter = request.args.get('status', '')
    assignee_filter = request.args.get('assignee', type=int)
    due_filter = request.args.get('due', '')
    sort = request.args.get('sort', 'due_date')
    order = request.args.get('order', 'asc')

    today = date.today()
    soon = today + timedelta(days=7)
    query = Task.query

    if status_filter:
        query = query.filter(Task.status == status_filter)
    if assignee_filter:
        query = query.filter(Task.assigned_to_id == assignee_filter)

    if due_filter == 'overdue':
        query = query.filter(Task.due_date < today, Task.status != 'done')
    elif due_filter == 'soon':
        query = query.filter(Task.due_date >= today, Task.due_date <= soon, Task.status != 'done')
    elif due_filter == 'open':
        query = query.filter(Task.status != 'done')

    sort_col = {
        'due_date':   Task.due_date,
        'status':     Task.status,
        'created_at': Task.created_at,
        'title':      Task.title,
    }.get(sort, Task.due_date)

    query = query.order_by(sort_col.asc() if order == 'asc' else sort_col.desc())

    tasks = query.all()
    users = User.query.order_by(User.name).all()

    overdue_count = Task.query.filter(Task.due_date < today, Task.status != 'done').count()
    due_soon_count = Task.query.filter(Task.due_date >= today, Task.due_date <= soon, Task.status != 'done').count()

    return render_template(
        'tasks/list.html',
        tasks=tasks,
        users=users,
        status_filter=status_filter,
        assignee_filter=assignee_filter,
        due_filter=due_filter,
        sort=sort,
        order=order,
        today=today,
        overdue_count=overdue_count,
        due_soon_count=due_soon_count,
    )


# ── Create ───────────────────────────────────────────────────────────────────

@tasks_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_task():
    form = TaskForm()
    form.populate_choices()

    if request.method == 'GET':
        asset_id = request.args.get('asset_id', type=int)
        if asset_id:
            form.asset_id.data = asset_id
        form.assigned_to_id.data = current_user.id

    if form.validate_on_submit():
        task = Task(
            title=form.title.data.strip(),
            asset_id=form.asset_id.data or None,
            assigned_to_id=form.assigned_to_id.data or None,
            due_date=form.due_date.data,
            status=form.status.data,
            notes=form.notes.data.strip() or None,
        )
        db.session.add(task)
        db.session.commit()
        flash('המשימה נוצרה בהצלחה.', 'success')
        return redirect(url_for('tasks.list_tasks'))

    return render_template('tasks/form.html', form=form, task=None, title='משימה חדשה')


# ── Edit ─────────────────────────────────────────────────────────────────────

@tasks_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    task = Task.query.get_or_404(id)
    form = TaskForm(obj=task)
    form.populate_choices()

    if form.validate_on_submit():
        task.title = form.title.data.strip()
        task.asset_id = form.asset_id.data or None
        task.assigned_to_id = form.assigned_to_id.data or None
        task.due_date = form.due_date.data
        task.status = form.status.data
        task.notes = form.notes.data.strip() or None
        db.session.commit()
        flash('המשימה עודכנה בהצלחה.', 'success')
        return redirect(url_for('tasks.list_tasks'))

    return render_template('tasks/form.html', form=form, task=task, title='עריכת משימה')


# ── Quick actions ─────────────────────────────────────────────────────────────

@tasks_bp.route('/<int:id>/done', methods=['POST'])
@login_required
def mark_done(id):
    task = Task.query.get_or_404(id)
    task.status = 'done'
    db.session.commit()
    flash(f'"{task.title}" סומנה כהושלמה.', 'success')
    return redirect(request.referrer or url_for('tasks.list_tasks'))


@tasks_bp.route('/<int:id>/reopen', methods=['POST'])
@login_required
def reopen(id):
    task = Task.query.get_or_404(id)
    task.status = 'pending'
    db.session.commit()
    flash(f'"{task.title}" נפתחה מחדש.', 'info')
    return redirect(request.referrer or url_for('tasks.list_tasks'))


@tasks_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    if not current_user.is_admin:
        abort(403)
    task = Task.query.get_or_404(id)
    title = task.title
    db.session.delete(task)
    db.session.commit()
    flash(f'המשימה "{title}" נמחקה.', 'warning')
    return redirect(url_for('tasks.list_tasks'))
