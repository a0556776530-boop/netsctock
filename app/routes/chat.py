from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from flask_socketio import emit

from app.models.chat_message import ChatMessage

chat_bp = Blueprint('chat', __name__, url_prefix='/chat')

_MAX_HISTORY = 100


@chat_bp.route('/')
@login_required
def room():
    messages = list(
        ChatMessage.objects.order_by('-timestamp').limit(_MAX_HISTORY)
    )
    messages.reverse()
    return render_template('chat/room.html', messages=messages)


def register_socket_events(socketio):

    @socketio.on('connect', namespace='/chat')
    def on_connect():
        if not current_user.is_authenticated:
            return False

    @socketio.on('send_message', namespace='/chat')
    def on_send_message(data):
        if not current_user.is_authenticated:
            return
        text = (data.get('text') or '').strip()[:2000]
        if not text:
            return
        msg = ChatMessage(
            user_id  =str(current_user.id),
            user_name=current_user.name,
            user_role=current_user.role,
            text     =text,
        )
        msg.save()
        emit('new_message', msg.to_dict(), broadcast=True, namespace='/chat')
