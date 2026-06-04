"""
WebSocket event handlers for real-time chat (Flask-SocketIO).
Imported once at app startup via app/__init__.py.
"""
from datetime import datetime

import gevent
from bson import ObjectId as _BsonOID
from flask import request
from flask_login import current_user
from flask_socketio import emit, join_room, leave_room

from app import socketio
from app.models.chat_message import ChatMessage, _private_room
from app.models.chat_group   import ChatGroup
from app.models.user         import User
from app.routes.chat         import _can_access_room, _is_online, _ONLINE_MINS


# ── Connection ────────────────────────────────────────────────────────────────

@socketio.on('connect')
def on_connect():
    if not current_user.is_authenticated:
        return False   # refuse unauthenticated socket connections


@socketio.on('disconnect')
def on_disconnect():
    pass


# ── Join / leave room ─────────────────────────────────────────────────────────

@socketio.on('chat_join')
def on_chat_join(data):
    if not current_user.is_authenticated:
        return
    room = data.get('room')
    if room and _can_access_room(str(current_user.id), room):
        join_room(room)
        emit('chat_joined', {'room': room})


@socketio.on('chat_leave')
def on_chat_leave(data):
    if not current_user.is_authenticated:
        return
    room = data.get('room')
    if room:
        leave_room(room)


# ── Send message ──────────────────────────────────────────────────────────────

@socketio.on('chat_send')
def on_chat_send(data):
    if not current_user.is_authenticated:
        return

    room_key    = (data.get('room') or 'group').strip()
    text        = (data.get('text') or '').strip()[:4000]
    tmp_id      = data.get('tmp_id', '')
    receiver_id = data.get('receiver_id') or ''
    reply_to_id = data.get('reply_to_id') or ''

    if not text or not _can_access_room(str(current_user.id), room_key):
        return

    # Snapshot user context — current_user is not safe to access inside a greenlet
    uid   = str(current_user.id)
    uname = current_user.name
    urole = current_user.role or ''
    sid   = request.sid
    ts    = datetime.utcnow()

    # Quick lookups (fast index reads — stay synchronous so msg_dict is complete)
    reply_text = reply_user = ''
    if reply_to_id:
        orig = ChatMessage.objects(id=reply_to_id).first()
        if orig and not orig.deleted:
            reply_text = (orig.text or '')[:200]
            reply_user = orig.user_name

    is_group_room = (room_key == 'group' or
                     room_key.startswith('ch_') or
                     room_key.startswith('grp_'))

    recv_online = False
    if receiver_id:
        other = User.objects(id=receiver_id).only('last_seen').first()
        if other:
            recv_online = _is_online(other)

    # Pre-generate the MongoDB ObjectId so we can broadcast before the DB write
    msg_id = _BsonOID()

    msg_dict = {
        'id':             str(msg_id),
        'user_id':        uid,
        'user_name':      uname,
        'user_role':      urole,
        'text':           text,
        'deleted':        False,
        'timestamp':      ts.strftime('%H:%M'),
        'date':           ts.strftime('%d/%m/%Y'),
        '_iso':           ts.isoformat(),
        'room':           room_key,
        'receiver_id':    receiver_id,
        'readers':        [uid],
        'read':           is_group_room,
        'reply_to_id':    reply_to_id,
        'reply_to_text':  reply_text,
        'reply_to_user':  reply_user,
        'reactions':      {},
        'file_id':        '',
        'file_name':      '',
        'file_type':      '',
        'file_size':      0,
        'has_file':       False,
        'edited':         False,
        'forwarded':      False,
        'forward_from':   '',
        'receiver_online': recv_online,
    }

    # 1. Broadcast IMMEDIATELY — before any DB write
    emit('chat_message', msg_dict, to=room_key)
    if tmp_id:
        emit('chat_confirmed', {
            'tmp_id':  tmp_id,
            'real_id': str(msg_id),
            '_iso':    ts.isoformat(),
        }, to=sid)

    # 2. Persist asynchronously — does not block the WebSocket response
    def _persist():
        try:
            msg = ChatMessage(
                id            = msg_id,
                user_id       = uid,
                user_name     = uname,
                user_role     = urole,
                text          = text,
                room          = room_key,
                receiver_id   = receiver_id,
                read          = is_group_room,
                reply_to_id   = reply_to_id,
                reply_to_text = reply_text,
                reply_to_user = reply_user,
                reactions     = {},
                readers       = [uid],
                timestamp     = ts,
            )
            msg.save(force_insert=True)
        except Exception:
            import traceback
            traceback.print_exc()

    gevent.spawn(_persist)


# ── Typing indicator ──────────────────────────────────────────────────────────

@socketio.on('chat_typing')
def on_typing(data):
    if not current_user.is_authenticated:
        return
    room = data.get('room')
    if not room:
        return
    emit('chat_typing', {
        'user':    current_user.name,
        'user_id': str(current_user.id),
    }, to=room, include_self=False)
