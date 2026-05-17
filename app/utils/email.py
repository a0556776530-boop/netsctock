from datetime import date, timedelta
from flask import current_app, url_for
from flask_mail import Message

from app import mail
from app.models.task import Task
from app.models.asset import Asset
from app.models.user import User


def send_due_reminders():
    """
    Send one digest email per user who has overdue or due-soon items.
    Admins also receive a full system summary.
    Returns the number of emails sent.
    """
    today = date.today()
    soon = today + timedelta(days=7)
    sent = 0

    users = User.query.all()
    for user in users:
        overdue_tasks = Task.query.filter(
            Task.assigned_to_id == user.id,
            Task.due_date < today,
            Task.status != 'done'
        ).order_by(Task.due_date).all()

        soon_tasks = Task.query.filter(
            Task.assigned_to_id == user.id,
            Task.due_date >= today,
            Task.due_date <= soon,
            Task.status != 'done'
        ).order_by(Task.due_date).all()

        overdue_assets = Asset.query.filter(
            Asset.assigned_to_id == user.id,
            Asset.due_date < today,
            Asset.status != 'retired'
        ).order_by(Asset.due_date).all()

        soon_assets = Asset.query.filter(
            Asset.assigned_to_id == user.id,
            Asset.due_date >= today,
            Asset.due_date <= soon,
            Asset.status != 'retired'
        ).order_by(Asset.due_date).all()

        if overdue_tasks or soon_tasks or overdue_assets or soon_assets:
            _send_user_digest(user, overdue_tasks, soon_tasks, overdue_assets, soon_assets, today)
            sent += 1

    # Admin summary: all overdue items across all users
    all_admins = User.query.filter_by(role='admin').all()
    for admin in all_admins:
        all_overdue_tasks = Task.query.filter(
            Task.due_date < today, Task.status != 'done'
        ).order_by(Task.due_date).all()
        all_overdue_assets = Asset.query.filter(
            Asset.due_date < today, Asset.status != 'retired'
        ).order_by(Asset.due_date).all()

        if all_overdue_tasks or all_overdue_assets:
            _send_admin_summary(admin, all_overdue_tasks, all_overdue_assets, today)
            sent += 1

    return sent


def _send_user_digest(user, overdue_tasks, soon_tasks, overdue_assets, soon_assets, today):
    subject = f'[Inventory] Due Date Reminder — {today.strftime("%d %b %Y")}'
    html = _build_user_html(user, overdue_tasks, soon_tasks, overdue_assets, soon_assets)
    _send(user.email, subject, html)


def _send_admin_summary(admin, all_overdue_tasks, all_overdue_assets, today):
    subject = f'[Inventory] System Overdue Summary — {today.strftime("%d %b %Y")}'
    html = _build_admin_html(all_overdue_tasks, all_overdue_assets, today)
    _send(admin.email, subject, html)


def _send(to, subject, html):
    try:
        msg = Message(subject=subject, recipients=[to], html=html)
        mail.send(msg)
    except Exception as e:
        current_app.logger.error(f'Failed to send email to {to}: {e}')


# ── HTML builders ─────────────────────────────────────────────────────────────

_BASE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  body {{ font-family: Arial, sans-serif; color: #212529; font-size: 14px; margin: 0; background: #f8f9fa; }}
  .wrap {{ max-width: 600px; margin: 24px auto; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,.1); }}
  .header {{ background: #0d6efd; color: #fff; padding: 20px 24px; }}
  .header h1 {{ margin: 0; font-size: 20px; }}
  .header p  {{ margin: 4px 0 0; font-size: 13px; opacity: .85; }}
  .body {{ padding: 24px; }}
  h2 {{ font-size: 15px; margin: 20px 0 10px; border-bottom: 1px solid #dee2e6; padding-bottom: 6px; }}
  h2.overdue  {{ color: #dc3545; }}
  h2.soon     {{ color: #fd7e14; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 16px; font-size: 13px; }}
  th {{ background: #f1f3f5; text-align: left; padding: 6px 10px; }}
  td {{ padding: 6px 10px; border-bottom: 1px solid #f1f3f5; }}
  .badge-danger  {{ background:#fde8ea; color:#dc3545; border-radius:4px; padding:2px 7px; font-size:12px; }}
  .badge-warning {{ background:#fff3cd; color:#856404; border-radius:4px; padding:2px 7px; font-size:12px; }}
  a {{ color: #0d6efd; text-decoration: none; }}
  .footer {{ background:#f8f9fa; color:#6c757d; font-size:12px; text-align:center; padding:14px; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="header">
    <h1>&#128276; Inventory — Due Date Reminder</h1>
    <p>{date_str}</p>
  </div>
  <div class="body">
    {greeting}
    {sections}
  </div>
  <div class="footer">Inventory Hardware Asset Tracker &mdash; This is an automated reminder.</div>
</div>
</body>
</html>
"""


def _task_rows(tasks):
    rows = ''
    for t in tasks:
        asset_link = f'<a href="#">{t.asset.serial_number}</a>' if t.asset else '—'
        due = t.due_date.strftime('%d %b %Y') if t.due_date else '—'
        overdue_badge = '<span class="badge-danger">Overdue</span> ' if t.is_overdue else ''
        rows += f'<tr><td>{t.title}</td><td>{asset_link}</td><td>{overdue_badge}{due}</td></tr>'
    return rows


def _asset_rows(assets):
    rows = ''
    for a in assets:
        due = a.due_date.strftime('%d %b %Y') if a.due_date else '—'
        overdue_badge = '<span class="badge-danger">Overdue</span> ' if a.is_overdue else ''
        rows += f'<tr><td><strong>{a.serial_number}</strong></td><td>{a.asset_type.name if a.asset_type else "—"}</td><td>{a.model or "—"}</td><td>{overdue_badge}{due}</td></tr>'
    return rows


def _task_table(tasks, heading, cls):
    if not tasks:
        return ''
    rows = _task_rows(tasks)
    return f'''
    <h2 class="{cls}">{heading} ({len(tasks)})</h2>
    <table>
      <tr><th>Task</th><th>Asset</th><th>Due Date</th></tr>
      {rows}
    </table>'''


def _asset_table(assets, heading, cls):
    if not assets:
        return ''
    rows = _asset_rows(assets)
    return f'''
    <h2 class="{cls}">{heading} ({len(assets)})</h2>
    <table>
      <tr><th>Serial Number</th><th>Type</th><th>Model</th><th>Due Date</th></tr>
      {rows}
    </table>'''


def _build_user_html(user, overdue_tasks, soon_tasks, overdue_assets, soon_assets):
    sections = (
        _task_table(overdue_tasks, '⚠ Overdue Tasks', 'overdue') +
        _task_table(soon_tasks, '📅 Tasks Due This Week', 'soon') +
        _asset_table(overdue_assets, '⚠ Overdue Assets', 'overdue') +
        _asset_table(soon_assets, '📅 Assets Due This Week', 'soon')
    )
    return _BASE.format(
        date_str=date.today().strftime('%d %B %Y'),
        greeting=f'<p>Hi <strong>{user.name}</strong>, here is your due date summary:</p>',
        sections=sections,
    )


def _build_admin_html(all_overdue_tasks, all_overdue_assets, today):
    sections = (
        _task_table(all_overdue_tasks, '⚠ All Overdue Tasks (System)', 'overdue') +
        _asset_table(all_overdue_assets, '⚠ All Overdue Assets (System)', 'overdue')
    )
    return _BASE.format(
        date_str=today.strftime('%d %B %Y'),
        greeting='<p>Admin summary of all overdue items across the system:</p>',
        sections=sections,
    )
