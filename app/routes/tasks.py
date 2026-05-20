from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, g
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Optional, Length

from app.models.task import Task
from app.models.asset import Asset
from app.models.user import User
from app.utils.translations import localize_form
from app.utils.mongo_helpers import get_or_404

tasks_bp = Blueprint('tasks', __name__, url_prefix='/tasks')


def _asset_choices():
    assets = list(Asset.objects.order_by('serial_number'))
    return [('', '— None —')] + [
        (str(a.id), f'{a.serial_number}  ({a.asset_type.name if a.asset_type else "?"})')
        for a in assets
    ]


def _user_choices():
    users = list(User.objects.order_by('name'))
    return [('', '— None —')] + [(str(u.id), u.name) for u in users]


class TaskForm(FlaskForm):
    title          = StringField('Task Title', validators=[DataRequired(), Length(max=255)])
    asset_id       = SelectField('Related Asset',  coerce=str, validators=[Optional()])
    assigned_to_id = SelectField('Assigned To',    coerce=str, validators=[Optional()])
    status         = SelectField('Status', choices=[
        ('pending', 'Pending'), ('in_progress', 'In Progress'), ('done', 'Done'),
    ])
    notes  = TextAreaField('Notes', validators=[Optional()])
    submit = SubmitField('Save Task')

    def populate_choices(self):
        self.asset_id.choices       = _asset_choices()
        self.assigned_to_id.choices = _user_choices()


def _localize_task_form(form, t):
    localize_form(form, t, submit_key='form_save_task')
    form.status.choices = [
        ('pending',     t.get('task_status_pending',     'Pending')),
        ('in_progress', t.get('task_status_in_progress', 'In Progress')),
        ('done',        t.get('task_status_done',        'Done')),
    ]
    return form


@tasks_bp.route('/')
@login_required
def list_tasks():
    status_filter   = request.args.get('status', '')
    assignee_filter = request.args.get('assignee', '')
    sort            = request.args.get('sort', 'created_at')
    order           = request.args.get('order', 'desc')

    qs = Task.objects
    if status_filter:
        qs = qs(status=status_filter)
    if assignee_filter:
        user_obj = User.objects(id=assignee_filter).first()
        if user_obj:
            qs = qs(assignee=user_obj)

    sort_field = {'status': 'status', 'created_at': 'created_at', 'title': 'title'}.get(sort, 'created_at')
    qs = qs.order_by(sort_field if order == 'asc' else f'-{sort_field}')

    tasks = list(qs.select_related())
    users = list(User.objects.order_by('name'))

    return render_template(
        'tasks/list.html',
        tasks=tasks, users=users,
        status_filter=status_filter, assignee_filter=assignee_filter,
        sort=sort, order=order,
    )


@tasks_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_task():
    t = getattr(g, 't', {})
    form = TaskForm()
    form.populate_choices()
    _localize_task_form(form, t)

    if request.method == 'GET':
        asset_id = request.args.get('asset_id', '')
        if asset_id:
            form.asset_id.data = asset_id
        form.assigned_to_id.data = str(current_user.id)

    if form.validate_on_submit():
        asset   = Asset.objects(id=form.asset_id.data).first()   if form.asset_id.data   else None
        assignee = User.objects(id=form.assigned_to_id.data).first() if form.assigned_to_id.data else None
        task = Task(
            title=form.title.data.strip(),
            asset=asset,
            assignee=assignee,
            status=form.status.data,
            notes=form.notes.data.strip() or None,
        )
        task.save()
        flash(t.get('flash_task_created', 'Task created successfully.'), 'success')
        return redirect(url_for('tasks.list_tasks'))

    return render_template('tasks/form.html', form=form, task=None,
                           title=t.get('form_title_new_task', 'New Task'))


@tasks_bp.route('/<id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    t = getattr(g, 't', {})
    task = get_or_404(Task, id)
    form = TaskForm()
    form.populate_choices()
    _localize_task_form(form, t)

    if request.method == 'GET':
        form.title.data          = task.title
        form.asset_id.data       = str(task.asset.id)    if task.asset    else ''
        form.assigned_to_id.data = str(task.assignee.id) if task.assignee else ''
        form.status.data         = task.status
        form.notes.data          = task.notes or ''

    if form.validate_on_submit():
        task.title    = form.title.data.strip()
        task.asset    = Asset.objects(id=form.asset_id.data).first()       if form.asset_id.data       else None
        task.assignee = User.objects(id=form.assigned_to_id.data).first()  if form.assigned_to_id.data else None
        task.status   = form.status.data
        task.notes    = form.notes.data.strip() or None
        task.save()
        flash(t.get('flash_task_updated', 'Task updated successfully.'), 'success')
        return redirect(url_for('tasks.list_tasks'))

    return render_template('tasks/form.html', form=form, task=task,
                           title=t.get('form_title_edit_task', 'Edit Task'))


@tasks_bp.route('/<id>/done', methods=['POST'])
@login_required
def mark_done(id):
    t = getattr(g, 't', {})
    task = get_or_404(Task, id)
    task.status = 'done'
    task.save()
    flash(t.get('flash_task_done', '"{title}" marked as done.').format(title=task.title), 'success')
    return redirect(request.referrer or url_for('tasks.list_tasks'))


@tasks_bp.route('/<id>/reopen', methods=['POST'])
@login_required
def reopen(id):
    t = getattr(g, 't', {})
    task = get_or_404(Task, id)
    task.status = 'pending'
    task.save()
    flash(t.get('flash_task_reopened', '"{title}" reopened.').format(title=task.title), 'info')
    return redirect(request.referrer or url_for('tasks.list_tasks'))


@tasks_bp.route('/<id>/delete', methods=['POST'])
@login_required
def delete(id):
    if not current_user.is_admin:
        abort(403)
    t = getattr(g, 't', {})
    task = get_or_404(Task, id)
    title = task.title
    task.delete()
    flash(t.get('flash_task_deleted', 'Task "{title}" deleted.').format(title=title), 'warning')
    return redirect(url_for('tasks.list_tasks'))
