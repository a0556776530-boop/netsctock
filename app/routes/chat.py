from flask import Blueprint, render_template, abort
from flask_login import login_required, current_user
from flask_socketio import emit, join_room

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
    return render_template('chat/room.html', messages=messages, chat_mode='group')


@chat_bp.route('/inbox')
@login_required
def inbox():
    me_id = str(current_user.id)
    all_users = [u for u in User.objects.order_by('name') if str(u.id) != me_id]

    # For each user, get last message and unread count
    conversations = []
    for u in all_users:
        room_key = _private_room(me_id, str(u.id))
        last_msg = ChatMessage.objects(room=room_key).order_by('-timestamp').first()
        unread = ChatMessage.objects(
            room=room_key,
            receiver_id=me_id,
            read=False,
        ).count()
        conversations.append({
            'user': u,
            'last_msg': last_msg,
            'unread': unread,
        })

    # Sort: conversations with messages first, then alphabetical
    conversations.sort(key=lambda c: (
        c['last_msg'].timestamp if c['last_msg'] else None
    ) or __import__('datetime').datetime.min, reverse=True)

    return render_template('chat/inbox.html', conversations=conversations)


@chat_bp.route('/with/<user_id>')
@login_required
def private(user_id):
    other = User.objects(id=user_id).first()
    if not other or str(other.id) == str(current_user.id):
        abort(404)

    room_key = _private_room(str(current_user.id), str(other.id))

    # Mark messages as read
    ChatMessage.objects(
        room=room_key,
        receiver_id=str(current_user.id),
        read=False,
    ).update(set__read=True)

    messages = list(
        ChatMessage.objects(room=room_key).order_by('-timestamp').limit(_MAX_HISTORY)
    )
    messages.reverse()
    return render_template('chat/room.html',
                           messages=messages,
                           chat_mode='private',
                           other_user=other,
                           room_key=room_key)


def register_socket_events(socketio):

    @socketio.on('connect', namespace='/chat')
    def on_connect():
        if not current_user.is_authenticated:
            return False

    @socketio.on('join', namespace='/chat')
    def on_join(data):
        if not current_user.is_authenticated:
            return
        room_key = data.get('room', 'group')
        join_room(room_key)

    @socketio.on('send_message', namespace='/chat')
    def on_send_message(data):
        if not current_user.is_authenticated:
            return
        text = (data.get('text') or '').strip()[:2000]
        if not text:
            return

        room_key    = data.get('room', 'group')
        receiver_id = data.get('receiver_id') or None

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

        payload = msg.to_dict()
        if room_key == 'group':
            emit('new_message', payload, broadcast=True, namespace='/chat')
        else:
            emit('new_message', payload, to=room_key, namespace='/chat')
            # Badge update to receiver
            unread = ChatMessage.objects(
                room=room_key, receiver_id=receiver_id, read=False
            ).count()
            emit('unread_update', {'room': room_key, 'count': unread},
                 to=room_key, namespace='/chat')
