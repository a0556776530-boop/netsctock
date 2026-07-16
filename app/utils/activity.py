from app.models.activity import ActivityLog

_ICONS = {
    'asset_created':        ('bi-plus-circle-fill',      'success'),
    'asset_edited':         ('bi-pencil-fill',           'secondary'),
    'asset_assigned':       ('bi-person-check-fill',     'primary'),
    'asset_moved':          ('bi-arrow-left-right',      'info'),
    'asset_returned':       ('bi-arrow-return-left',     'info'),
    'estimate_created':     ('bi-file-earmark-plus-fill','primary'),
    'estimate_edited':      ('bi-file-earmark-text-fill','secondary'),
    'estimate_completed':   ('bi-check-circle-fill',     'success'),
    'estimate_withdrawn':   ('bi-archive-fill',          'warning'),
    'purchase_created':     ('bi-cart-plus-fill',        'primary'),
    'purchase_updated':     ('bi-cart-fill',             'secondary'),
    'purchase_status':      ('bi-arrow-repeat',          'info'),
    'purchase_received':    ('bi-box-seam-fill',         'success'),
    'task_created':         ('bi-list-task',             'primary'),
    'task_completed':       ('bi-check2-circle',         'success'),
    'task_reopened':        ('bi-arrow-clockwise',       'warning'),
}


def log_activity(user, action_type, description):
    icon, color = _ICONS.get(action_type, ('bi-circle', 'secondary'))
    try:
        ActivityLog(
            user_name=user.name,
            user_role=getattr(user, 'role', ''),
            action_type=action_type,
            description=description,
            icon=icon,
            color=color,
        ).save()
    except Exception:
        pass  # never break the main flow
