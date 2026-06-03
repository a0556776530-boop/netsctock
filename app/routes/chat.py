from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, abort
from flask_login import login_required, current_user

from app.models.chat_message import ChatMessage, _private_room
from app.models.user import User

chat_bp = Blueprint('chat', __name__, url_prefix='/chat')

_MAX_HISTORY = 100


@chat_bp.route('/')
@login_required
def room():
    messages = list(
        ChatMessage.objects(room='group').order_by('-timestamp').limit(_MAX_HISTORY)
    )
    messages.reverse()
    return render_template('chat/room.html', messages=messages,
                           chat_mode='group', room_key='group')


@chat_bp.route('/inbox')
@login_required
def inbox():
    me_id = str(current_user.id)
    all_users = [u for u in User.objects.order_by('name') if str(u.id) != me_id]

    conversations = []
    for u in all_users:
        room_key = _private_room(me_id, str(u.id))
        last_msg = ChatMessage.objects(room=room_key).order_by('-timestamp').first()
        unread   = ChatMessage.objects(room=room_key, receiver_id=me_id, read=False).count()
        conversations.append({'user': u, 'last_msg': last_msg, 'unread': unread})

    conversations.sort(
        key=lambda c: c['last_msg'].timestamp if c['last_msg'] else datetime.min,
        reverse=True,
    )
    return render_template('chat/inbox.html', conversations=conversations)


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
                           chat_mode='private', other_user=other, room_key=room_key)


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

    msg = ChatMessage(
        user_id    =str(current_user.id),
        user_name  =current_user.name,
        user_role  =current_user.role,
        text       =text,
        room       =room_key,
        receiver_id=receiver_id,
        read       =(room_key == 'group'),
    )
    msg.save()
    return jsonify(ok=True, message=msg.to_dict())


@chat_bp.route('/api/messages')
@login_required
def api_messages():
    room_key = request.args.get('room', 'group')
    since    = request.args.get('since')

    qs = ChatMessage.objects(room=room_key)
    if since:
        try:
            dt = datetime.fromisoformat(since)
            qs = qs.filter(timestamp__gt=dt)
        except ValueError:
            pass

    messages = list(qs.order_by('timestamp').limit(50))

    # Mark private messages as read
    if room_key != 'group':
        ChatMessage.objects(
            room=room_key, receiver_id=str(current_user.id), read=False
        ).update(set__read=True)

    return jsonify(messages=[m.to_dict() for m in messages])
