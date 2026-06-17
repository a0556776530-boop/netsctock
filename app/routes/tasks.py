from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, g
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from mongoengine import Q
from wtforms import StringField, SelectField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Optional, Length

from app.models.task import Task
from app.models.pool import Pool
from app.utils.mongo_helpers import get_or_404

tasks_bp = Blueprint('tasks', __name__, url_prefix='/tasks')


class TaskForm(FlaskForm):
    title         = StringField('Task Title',   validators=[DataRequired(), Length(max=255)])
    assignee_name = StringField('Assigned To',  validators=[Optional(), Length(max=200)])
    status        = SelectField('Status', choices=[
        ('in_progress', 'In Progress'), ('done', 'Done'),
    ])
    notes  = TextAreaField('Notes', validators=[Optional()])
    submit = SubmitField('Save Task')


@tasks_bp.route('/')
@login_required
def list_tasks():
    sort  = request.args.get('sort', 'created_at')
    order = request.args.get('order', 'desc')

    qs = Task.objects(__raw__={'status': {'$in': ['pending', 'in_progress']}})

    sort_field = {'created_at': 'created_at', 'title': 'title'}.get(sort, 'created_at')
    qs = qs.order_by(sort_field if order == 'asc' else f'-{sort_field}')

    tasks = list(qs)
    return render_template(
        'tasks/list.html',
        tasks=tasks,
        sort=sort, order=order,
    )


@tasks_bp.route('/history')
@login_required
def history():
    tasks = list(Task.objects(status='done').order_by('-created_at'))
    return render_template('tasks/history.html', tasks=tasks)


@tasks_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_task():
    if not current_user.can_edit:
        abort(403)
    t    = getattr(g, 't', {})
    form = TaskForm()

    active_pools = list(Pool.objects(Q(is_active=True) | Q(is_active__exists=False)).order_by('name').only('id', 'name', 'emf_number', 'currency', 'total_amount', 'consumed_amount'))

    if form.validate_on_submit():
        pool_id = (request.form.get('pool_id') or '').strip()
        selected_pool = Pool.objects(id=pool_id).first() if pool_id else None
        task = Task(
            title=form.title.data.strip(),
            assignee_name=(form.assignee_name.data or '').strip() or None,
            status=form.status.data,
            notes=(form.notes.data or '').strip() or None,
            pool=selected_pool,
        )
        task.save()
        flash('Task created successfully.', 'success')
        return redirect(url_for('tasks.list_tasks'))

    return render_template('tasks/form.html', form=form, task=None, title='New Task', active_pools=active_pools)


@tasks_bp.route('/<id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    if not current_user.can_edit:
        abort(403)
    task = get_or_404(Task, id)
    form = TaskForm()
    active_pools = list(Pool.objects(Q(is_active=True) | Q(is_active__exists=False)).order_by('name').only('id', 'name', 'emf_number', 'currency', 'total_amount', 'consumed_amount'))

    if request.method == 'GET':
        form.title.data         = task.title
        form.assignee_name.data = task.assignee_name or ''
        form.status.data        = task.status if task.status in ('in_progress', 'done') else 'in_progress'
        form.notes.data         = task.notes or ''

    if form.validate_on_submit():
        pool_id = (request.form.get('pool_id') or '').strip()
        task.title         = form.title.data.strip()
        task.assignee_name = (form.assignee_name.data or '').strip() or None
        task.status        = form.status.data
        task.notes         = (form.notes.data or '').strip() or None
        task.pool          = Pool.objects(id=pool_id).first() if pool_id else None
        task.save()
        flash('Task updated successfully.', 'success')
        return redirect(url_for('tasks.list_tasks'))

    return render_template('tasks/form.html', form=form, task=task, title='Edit Task', active_pools=active_pools)


@tasks_bp.route('/<id>/done', methods=['POST'])
@login_required
def mark_done(id):
    if not current_user.can_edit:
        abort(403)
    task = get_or_404(Task, id)
    task.status = 'done'
    task.save()
    flash(f'"{task.title}" marked as done.', 'success')
    return redirect(request.referrer or url_for('tasks.list_tasks'))


@tasks_bp.route('/<id>/reopen', methods=['POST'])
@login_required
def reopen(id):
    if not current_user.can_edit:
        abort(403)
    task = get_or_404(Task, id)
    task.status = 'in_progress'
    task.save()
    flash(f'"{task.title}" reopened.', 'info')
    return redirect(request.referrer or url_for('tasks.list_tasks'))


@tasks_bp.route('/<id>/delete', methods=['POST'])
@login_required
def delete(id):
    if not current_user.is_admin:
        abort(403)
    task = get_or_404(Task, id)
    title = task.title
    task.delete()
    flash(f'Task "{title}" deleted.', 'warning')
    return redirect(url_for('tasks.list_tasks'))
