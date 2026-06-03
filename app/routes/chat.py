from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, jsonify, abort, redirect, url_for, flash, g
from flask_login import login_required, current_user

from app.models.chat_message import ChatMessage, _private_room
from app.models.chat_group import ChatGroup
from app.models.user import User

chat_bp = Blueprint('chat', __name__, url_prefix='/chat')

_MAX_HISTORY  = 100
_ONLINE_MINS  = 3   # last_seen within this = online


def _is_online(user):
    if not user.last_seen:
        return False
    return (datetime.utcnow() - user.last_seen) < timedelta(minutes=_ONLINE_MINS)


# ── Pages ─────────────────────────────────────────────────────────────────────

@chat_bp.route('/')
@login_required
def room():
    messages = list(
        ChatMessage.objects(room='group').order_by('-timestamp').limit(_MAX_HISTORY)
    )
    messages.reverse()
    return render_template('chat/room.html', messages=messages,
                           chat_mode='group', room_key='group',
                           room_title=g.t.get('chat_group_everyone', 'כולם'))


@chat_bp.route('/inbox')
@login_required
def inbox():
    me_id     = str(current_user.id)
    all_users = [u for u in User.objects.order_by('name') if str(u.id) != me_id]
    my_groups = ChatGroup.objects(member_ids=me_id).order_by('name')

    conversations = []
    for u in all_users:
        room_key = _private_room(me_id, str(u.id))
        last_msg = ChatMessage.objects(room=room_key).order_by('-timestamp').first()
        unread   = ChatMessage.objects(room=room_key, receiver_id=me_id, read=False).count()
        conversations.append({
            'user':    u,
            'online':  _is_online(u),
            'last_msg': last_msg,
            'unread':  unread,
        })
    conversations.sort(
        key=lambda c: c['last_msg'].timestamp if c['last_msg'] else datetime.min,
        reverse=True,
    )

    group_convs = []
    for grp in my_groups:
        last_msg = ChatMessage.objects(room=grp.room_key).order_by('-timestamp').first()
        group_convs.append({'group': grp, 'last_msg': last_msg})

    return render_template('chat/inbox.html',
                           conversations=conversations,
                           group_convs=group_convs)


@chat_bp.route('/with/<user_id>')
@login_required
def private(user_id):
    other = User.objects(id=user_id).first()
    if not other or str(other.id) == str(current_user.id):
        abort(404)
    room_key = _private_room(str(current_user.id), str(other.id))
    ChatMessage.objects(room=room_key, receiver_id=str(current_user.id), read=False)\
               .update(set__read=True)
    messages = list(
        ChatMessage.objects(room=room_key).order_by('-timestamp').limit(_MAX_HISTORY)
    )
    messages.reverse()
    return render_template('chat/room.html', messages=messages,
                           chat_mode='private', other_user=other, room_key=room_key,
                           room_title=other.name)


@chat_bp.route('/group/<group_id>')
@login_required
def group_room(group_id):
    grp = ChatGroup.objects(id=group_id).first()
    if not grp or not grp.is_member(current_user.id):
        abort(404)
    messages = list(
        ChatMessage.objects(room=grp.room_key).order_by('-timestamp').limit(_MAX_HISTORY)
    )
    messages.reverse()
    return render_template('chat/room.html', messages=messages,
                           chat_mode='group', room_key=grp.room_key,
                           room_title=grp.name)


@chat_bp.route('/groups')
@login_required
def groups():
    if not current_user.is_admin:
        abort(403)
    me_id     = str(current_user.id)
    all_groups = list(ChatGroup.objects.order_by('name'))
    all_users  = [u for u in User.objects.order_by('name') if str(u.id) != me_id]
    return render_template('chat/groups.html', groups=all_groups, all_users=all_users)


@chat_bp.route('/groups/new', methods=['POST'])
@login_required
def new_group():
    if not current_user.is_admin:
        abort(403)
    t       = getattr(g, 't', {})
    name    = (request.form.get('name') or '').strip()[:100]
    desc    = (request.form.get('description') or '').strip()[:300]
    members = request.form.getlist('members')
    if not name:
        flash(t.get('chat_group_name_required', 'שם קבוצה נדרש'), 'danger')
        return redirect(url_for('chat.groups'))
    members = list({str(current_user.id)} | set(members))
    grp = ChatGroup(name=name, description=desc,
                    creator_id=str(current_user.id), member_ids=members)
    grp.save()
    flash(t.get('chat_group_created', 'קבוצה נוצרה בהצלחה'), 'success')
    return redirect(url_for('chat.group_room', group_id=str(grp.id)))


@chat_bp.route('/groups/<group_id>/delete', methods=['POST'])
@login_required
def delete_group(group_id):
    if not current_user.is_admin:
        abort(403)
    grp = ChatGroup.objects(id=group_id).first()
    if grp:
        ChatMessage.objects(room=grp.room_key).delete()
        grp.delete()
    return redirect(url_for('chat.groups'))


# ── API ───────────────────────────────────────────────────────────────────────

@chat_bp.route('/api/send', methods=['POST'])
@login_required
def api_send():
    data        = request.get_json(force=True) or {}
    text        = (data.get('text') or '').strip()[:2000]
    room_key    = data.get('room', 'group')
    receiver_id = data.get('receiver_id') or None

    if not text:
        return jsonify(ok=False), 400

    # For private rooms, verify membership
    if room_key.startswith('grp_'):
        grp_id = room_key[4:]
        grp = ChatGroup.objects(id=grp_id).first()
        if not grp or not grp.is_member(current_user.id):
            return jsonify(ok=False), 403

    msg = ChatMessage(
        user_id    =str(current_user.id),
        user_name  =current_user.name,
        user_role  =current_user.role,
        text       =text,
        room       =room_key,
        receiver_id=receiver_id,
        read       =(room_key == 'group' or room_key.startswith('grp_')),
    )
    msg.save()
    return jsonify(ok=True, message=msg.to_dict())


@chat_bp.route('/api/messages')
@login_required
def api_messages():
    room_key = request.args.get('room', 'group')
    since    = request.args.get('since')

    # Verify access to private group rooms
    if room_key.startswith('grp_'):
        grp_id = room_key[4:]
        grp = ChatGroup.objects(id=grp_id).first()
        if not grp or not grp.is_member(current_user.id):
            return jsonify(messages=[])

    qs = ChatMessage.objects(room=room_key)
    if since:
        try:
            qs = qs.filter(timestamp__gt=datetime.fromisoformat(since))
        except ValueError:
            pass

    messages = list(qs.order_by('timestamp').limit(50))

    if room_key not in ('group',) and not room_key.startswith('grp_'):
        ChatMessage.objects(
            room=room_key, receiver_id=str(current_user.id), read=False
        ).update(set__read=True)

    return jsonify(messages=[m.to_dict() for m in messages])


@chat_bp.route('/api/inbox-status')
@login_required
def api_inbox_status():
    """Returns unread counts + online status for all conversations."""
    me_id = str(current_user.id)
    result = {}

    all_users = [u for u in User.objects.only('id', 'last_seen', 'role') if str(u.id) != me_id]
    for u in all_users:
        uid = str(u.id)
        room_key = _private_room(me_id, uid)
        unread = ChatMessage.objects(room=room_key, receiver_id=me_id, read=False).count()
        result[uid] = {'unread': unread, 'online': _is_online(u)}

    total_unread = sum(v['unread'] for v in result.values())
    return jsonify(users=result, total_unread=total_unread)
