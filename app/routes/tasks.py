from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, g
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Optional, Length

from app import db
from app.models.task import Task
from app.models.asset import Asset
from app.models.user import User
from app.utils.translations import localize_form

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
    title = StringField('Task Title', validators=[DataRequired(), Length(max=255)])
    asset_id = SelectField('Related Asset', coerce=int, validators=[Optional()])
    assigned_to_id = SelectField('Assigned To', coerce=int, validators=[Optional()])
    status = SelectField('Status', choices=[
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
    ])
    notes = TextAreaField('Notes', validators=[Optional()])
    submit = SubmitField('Save Task')

    def populate_choices(self):
        self.asset_id.choices = _asset_choices()
        self.assigned_to_id.choices = _user_choices()


def _localize_task_form(form, t):
    localize_form(form, t, submit_key='form_save_task')
    form.status.choices = [
        ('pending',     t.get('task_status_pending', 'Pending')),
        ('in_progress', t.get('task_status_in_progress', 'In Progress')),
        ('done',        t.get('task_status_done', 'Done')),
    ]
    return form


# ── List ─────────────────────────────────────────────────────────────────────

@tasks_bp.route('/')
@login_required
def list_tasks():
    status_filter = request.args.get('status', '')
    assignee_filter = request.args.get('assignee', type=int)
    sort = request.args.get('sort', 'created_at')
    order = request.args.get('order', 'desc')

    query = Task.query

    if status_filter:
        query = query.filter(Task.status == status_filter)
    if assignee_filter:
        query = query.filter(Task.assigned_to_id == assignee_filter)

    sort_col = {
        'status':     Task.status,
        'created_at': Task.created_at,
        'title':      Task.title,
    }.get(sort, Task.created_at)

    query = query.order_by(sort_col.asc() if order == 'asc' else sort_col.desc())

    tasks = query.all()
    users = User.query.order_by(User.name).all()

    return render_template(
        'tasks/list.html',
        tasks=tasks,
        users=users,
        status_filter=status_filter,
        assignee_filter=assignee_filter,
        sort=sort,
        order=order,
    )


# ── Create ───────────────────────────────────────────────────────────────────

@tasks_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_task():
    t = getattr(g, 't', {})
    form = TaskForm()
    form.populate_choices()
    _localize_task_form(form, t)

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
            status=form.status.data,
            notes=form.notes.data.strip() or None,
        )
        db.session.add(task)
        db.session.commit()
        flash(t.get('flash_task_created', 'Task created successfully.'), 'success')
        return redirect(url_for('tasks.list_tasks'))

    return render_template('tasks/form.html', form=form, task=None,
                           title=t.get('form_title_new_task', 'New Task'))


# ── Edit ─────────────────────────────────────────────────────────────────────

@tasks_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    t = getattr(g, 't', {})
    task = Task.query.get_or_404(id)
    form = TaskForm(obj=task)
    form.populate_choices()
    _localize_task_form(form, t)

    if form.validate_on_submit():
        task.title = form.title.data.strip()
        task.asset_id = form.asset_id.data or None
        task.assigned_to_id = form.assigned_to_id.data or None
        task.status = form.status.data
        task.notes = form.notes.data.strip() or None
        db.session.commit()
        flash(t.get('flash_task_updated', 'Task updated successfully.'), 'success')
        return redirect(url_for('tasks.list_tasks'))

    return render_template('tasks/form.html', form=form, task=task,
                           title=t.get('form_title_edit_task', 'Edit Task'))


# ── Quick actions ─────────────────────────────────────────────────────────────

@tasks_bp.route('/<int:id>/done', methods=['POST'])
@login_required
def mark_done(id):
    t = getattr(g, 't', {})
    task = Task.query.get_or_404(id)
    task.status = 'done'
    db.session.commit()
    flash(t.get('flash_task_done', '"{title}" marked as done.').format(title=task.title), 'success')
    return redirect(request.referrer or url_for('tasks.list_tasks'))


@tasks_bp.route('/<int:id>/reopen', methods=['POST'])
@login_required
def reopen(id):
    t = getattr(g, 't', {})
    task = Task.query.get_or_404(id)
    task.status = 'pending'
    db.session.commit()
    flash(t.get('flash_task_reopened', '"{title}" reopened.').format(title=task.title), 'info')
    return redirect(request.referrer or url_for('tasks.list_tasks'))


@tasks_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    if not current_user.is_admin:
        abort(403)
    t = getattr(g, 't', {})
    task = Task.query.get_or_404(id)
    title = task.title
    db.session.delete(task)
    db.session.commit()
    flash(t.get('flash_task_deleted', 'Task "{title}" deleted.').format(title=title), 'warning')
    return redirect(url_for('tasks.list_tasks'))
