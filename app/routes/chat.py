import base64
import mimetypes
from datetime import datetime, timedelta

from flask import (Blueprint, render_template, request, jsonify,
                   abort, redirect, url_for, flash, g)
from flask_login import login_required, current_user

from app.models.chat_message import ChatMessage, _private_room
from app.models.chat_group   import ChatGroup
from app.models.chat_typing  import ChatTyping
from app.models.user         import User

chat_bp = Blueprint('chat', __name__, url_prefix='/chat')

_MAX_HISTORY  = 100
_MAX_FILE_B   = 2 * 1024 * 1024   # 2 MB
_ONLINE_MINS  = 3
_REACTIONS    = ['👍', '❤️', '🔥', '✅', '😂', '😮']

_CHANNELS = [
    {'key': 'ch_it',          'name': 'IT Team',        'icon': 'bi-hdd-network'},
    {'key': 'ch_logistics',   'name': 'Logistics',      'icon': 'bi-truck'},
    {'key': 'ch_procurement', 'name': 'Procurement',    'icon': 'bi-bag-check'},
    {'key': 'ch_managers',    'name': 'Managers',       'icon': 'bi-briefcase'},
]


def _is_online(user):
    if not user.last_seen:
        return False
    return (datetime.utcnow() - user.last_seen) < timedelta(minutes=_ONLINE_MINS)


def _file_type(mime):
    if mime and mime.startswith('image/'):
        return 'image'
    if mime == 'application/pdf':
        return 'pdf'
    if 'excel' in mime or 'spreadsheet' in mime or mime.endswith('.sheet'):
        return 'excel'
    return 'file'


# ── Pages ─────────────────────────────────────────────────────────────────────

@chat_bp.route('/')
@login_required
def room():
    return redirect(url_for('chat.app'))


@chat_bp.route('/app')
@login_required
def app():
    me_id  = str(current_user.id)
    users  = [u for u in User.objects.order_by('name') if str(u.id) != me_id]
    groups = list(ChatGroup.objects(member_ids=me_id).order_by('name'))
    return render_template(
        'chat/app.html',
        users=users,
        groups=groups,
        channels=_CHANNELS,
        reactions=_REACTIONS,
        me_id=me_id,
    )


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
    return redirect(url_for('chat.app') + f'?room=grp_{grp.id}')


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


# ── API: conversations sidebar ─────────────────────────────────────────────────

@chat_bp.route('/api/conversations')
@login_required
def api_conversations():
    me_id  = str(current_user.id)
    me_obj = User.objects(id=me_id).first()
    pinned    = list(me_obj.pinned_rooms    or [])
    favorites = list(me_obj.favorite_rooms or [])

    result = []

    # 1. Channels
    for ch in _CHANNELS:
        last = ChatMessage.objects(room=ch['key']).order_by('-timestamp').first()
        result.append({
            'type':     'channel',
            'room':     ch['key'],
            'name':     ch['name'],
            'icon':     ch['icon'],
            'last_msg': last.text[:60] if last and not last.deleted else '',
            'last_ts':  last.timestamp.strftime('%H:%M') if last else '',
            'unread':   0,
            'online':   None,
            'pinned':   ch['key'] in pinned,
            'favorite': ch['key'] in favorites,
        })

    # 2. Groups
    for grp in ChatGroup.objects(member_ids=me_id).order_by('name'):
        rk   = grp.room_key
        last = ChatMessage.objects(room=rk).order_by('-timestamp').first()
        result.append({
            'type':     'group',
            'room':     rk,
            'name':     grp.name,
            'icon':     'bi-people-fill',
            'last_msg': last.text[:60] if last and not last.deleted else '',
            'last_ts':  last.timestamp.strftime('%H:%M') if last else '',
            'unread':   0,
            'online':   None,
            'pinned':   rk in pinned,
            'favorite': rk in favorites,
        })

    # 3. Everyone channel
    rk   = 'group'
    last = ChatMessage.objects(room=rk).order_by('-timestamp').first()
    result.insert(0, {
        'type':     'channel',
        'room':     rk,
        'name':     'כולם',
        'icon':     'bi-people',
        'last_msg': last.text[:60] if last and not last.deleted else '',
        'last_ts':  last.timestamp.strftime('%H:%M') if last else '',
        'unread':   0,
        'online':   None,
        'pinned':   rk in pinned,
        'favorite': rk in favorites,
    })

    # 4. Direct messages
    all_users = [u for u in User.objects.order_by('name') if str(u.id) != me_id]
    for u in all_users:
        rk     = _private_room(me_id, str(u.id))
        last   = ChatMessage.objects(room=rk).order_by('-timestamp').first()
        unread = ChatMessage.objects(room=rk, receiver_id=me_id, read=False).count()
        result.append({
            'type':      'dm',
            'room':      rk,
            'name':      u.name,
            'role':      u.role,
            'user_id':   str(u.id),
            'icon':      None,
            'last_msg':  last.text[:60] if last and not last.deleted else '',
            'last_ts':   last.timestamp.strftime('%H:%M') if last else '',
            'unread':    unread,
            'online':    _is_online(u),
            'pinned':    rk in pinned,
            'favorite':  rk in favorites,
        })

    return jsonify(conversations=result, pinned=pinned, favorites=favorites)


# ── API: messages ──────────────────────────────────────────────────────────────

@chat_bp.route('/api/messages')
@login_required
def api_messages():
    room_key = request.args.get('room', 'group')
    since    = request.args.get('since')

    # Access control for group rooms
    if room_key.startswith('grp_'):
        grp = ChatGroup.objects(id=room_key[4:]).first()
        if not grp or not grp.is_member(current_user.id):
            return jsonify(messages=[])

    qs = ChatMessage.objects(room=room_key)
    if since:
        try:
            qs = qs.filter(timestamp__gt=datetime.fromisoformat(since))
        except ValueError:
            pass
    else:
        qs = qs.order_by('-timestamp').limit(_MAX_HISTORY)
        qs = list(reversed(list(qs)))
        return jsonify(messages=[m.to_dict() for m in qs])

    messages = list(qs.order_by('timestamp').limit(50))

    # Mark PM messages as read when fetching
    if room_key.startswith('pm_'):
        ChatMessage.objects(
            room=room_key, receiver_id=str(current_user.id), read=False
        ).update(set__read=True, add_to_set__readers=str(current_user.id))

    return jsonify(messages=[m.to_dict() for m in messages])


@chat_bp.route('/api/file/<msg_id>')
@login_required
def api_file(msg_id):
    """Serve file data for a specific message."""
    msg = ChatMessage.objects(id=msg_id).first()
    if not msg or not msg.file_data:
        abort(404)
    return jsonify(file_data=msg.file_data, file_name=msg.file_name,
                   file_type=msg.file_type)


# ── API: send ──────────────────────────────────────────────────────────────────

@chat_bp.route('/api/send', methods=['POST'])
@login_required
def api_send():
    data        = request.get_json(force=True) or {}
    text        = (data.get('text') or '').strip()[:4000]
    room_key    = data.get('room', 'group')
    receiver_id = data.get('receiver_id') or None
    reply_to_id = data.get('reply_to_id') or None

    if not text and not data.get('has_file'):
        return jsonify(ok=False, error='empty'), 400

    # Access check
    if room_key.startswith('grp_'):
        grp = ChatGroup.objects(id=room_key[4:]).first()
        if not grp or not grp.is_member(current_user.id):
            return jsonify(ok=False, error='forbidden'), 403

    # Reply context
    reply_text = reply_user = ''
    if reply_to_id:
        orig = ChatMessage.objects(id=reply_to_id).first()
        if orig and not orig.deleted:
            reply_text = (orig.text or '')[:200]
            reply_user = orig.user_name

    is_group_room = room_key == 'group' or room_key.startswith('ch_') or room_key.startswith('grp_')

    msg = ChatMessage(
        user_id     =str(current_user.id),
        user_name   =current_user.name,
        user_role   =current_user.role,
        text        =text,
        room        =room_key,
        receiver_id =receiver_id,
        read        =is_group_room,
        reply_to_id =reply_to_id or '',
        reply_to_text=reply_text,
        reply_to_user=reply_user,
        reactions   ={},
        readers     =[str(current_user.id)],
    )
    msg.save()
    return jsonify(ok=True, message=msg.to_dict())


@chat_bp.route('/api/upload', methods=['POST'])
@login_required
def api_upload():
    room_key    = request.form.get('room', 'group')
    receiver_id = request.form.get('receiver_id') or None
    reply_to_id = request.form.get('reply_to_id') or None
    caption     = (request.form.get('caption') or '').strip()[:500]

    f = request.files.get('file')
    if not f:
        return jsonify(ok=False, error='no file'), 400

    raw = f.read()
    if len(raw) > _MAX_FILE_B:
        return jsonify(ok=False, error='too_large'), 400

    mime     = f.content_type or mimetypes.guess_type(f.filename)[0] or 'application/octet-stream'
    ftype    = _file_type(mime)
    b64data  = 'data:' + mime + ';base64,' + base64.b64encode(raw).decode()

    reply_text = reply_user = ''
    if reply_to_id:
        orig = ChatMessage.objects(id=reply_to_id).first()
        if orig and not orig.deleted:
            reply_text = (orig.text or '')[:200]
            reply_user = orig.user_name

    is_group_room = room_key == 'group' or room_key.startswith('ch_') or room_key.startswith('grp_')

    msg = ChatMessage(
        user_id     =str(current_user.id),
        user_name   =current_user.name,
        user_role   =current_user.role,
        text        =caption,
        room        =room_key,
        receiver_id =receiver_id,
        read        =is_group_room,
        reply_to_id =reply_to_id or '',
        reply_to_text=reply_text,
        reply_to_user=reply_user,
        file_data   =b64data,
        file_name   =f.filename,
        file_type   =ftype,
        file_size   =len(raw),
        reactions   ={},
        readers     =[str(current_user.id)],
    )
    msg.save()
    d = msg.to_dict()
    d['file_data'] = b64data
    return jsonify(ok=True, message=d)


# ── API: reactions ─────────────────────────────────────────────────────────────

@chat_bp.route('/api/react', methods=['POST'])
@login_required
def api_react():
    data   = request.get_json(force=True) or {}
    msg_id = data.get('msg_id')
    emoji  = data.get('emoji')
    if not msg_id or emoji not in _REACTIONS:
        return jsonify(ok=False), 400

    msg = ChatMessage.objects(id=msg_id).first()
    if not msg:
        return jsonify(ok=False), 404

    reactions = dict(msg.reactions or {})
    uid = str(current_user.id)
    if emoji not in reactions:
        reactions[emoji] = []
    if uid in reactions[emoji]:
        reactions[emoji].remove(uid)
        if not reactions[emoji]:
            del reactions[emoji]
    else:
        reactions[emoji].append(uid)

    msg.reactions = reactions
    msg.save()
    return jsonify(ok=True, reactions=reactions)


# ── API: delete ────────────────────────────────────────────────────────────────

@chat_bp.route('/api/delete/<msg_id>', methods=['POST'])
@login_required
def api_delete(msg_id):
    msg = ChatMessage.objects(id=msg_id).first()
    if not msg:
        return jsonify(ok=False), 404
    if msg.user_id != str(current_user.id) and not current_user.is_admin:
        return jsonify(ok=False), 403
    msg.deleted  = True
    msg.text     = ''
    msg.file_data= None
    msg.save()
    return jsonify(ok=True)


# ── API: read receipt ──────────────────────────────────────────────────────────

@chat_bp.route('/api/read', methods=['POST'])
@login_required
def api_read():
    data     = request.get_json(force=True) or {}
    room_key = data.get('room', '')
    uid      = str(current_user.id)
    if room_key.startswith('pm_'):
        ChatMessage.objects(
            room=room_key, receiver_id=uid, read=False
        ).update(set__read=True, add_to_set__readers=uid)
    return jsonify(ok=True)


# ── API: pin / favorite ────────────────────────────────────────────────────────

@chat_bp.route('/api/pin', methods=['POST'])
@login_required
def api_pin():
    data     = request.get_json(force=True) or {}
    room_key = data.get('room', '')
    me_obj   = User.objects(id=current_user.id).first()
    pinned   = list(me_obj.pinned_rooms or [])
    if room_key in pinned:
        pinned.remove(room_key)
    else:
        pinned.append(room_key)
    me_obj.pinned_rooms = pinned
    me_obj.save()
    return jsonify(ok=True, pinned=room_key in pinned)


@chat_bp.route('/api/favorite', methods=['POST'])
@login_required
def api_favorite():
    data     = request.get_json(force=True) or {}
    room_key = data.get('room', '')
    me_obj   = User.objects(id=current_user.id).first()
    favs     = list(me_obj.favorite_rooms or [])
    if room_key in favs:
        favs.remove(room_key)
    else:
        favs.append(room_key)
    me_obj.favorite_rooms = favs
    me_obj.save()
    return jsonify(ok=True, favorited=room_key in favs)


# ── API: typing ────────────────────────────────────────────────────────────────

@chat_bp.route('/api/typing', methods=['POST'])
@login_required
def api_typing_post():
    data     = request.get_json(force=True) or {}
    room_key = data.get('room', '')
    uid      = str(current_user.id)
    ChatTyping.objects(user_id=uid, room=room_key).update_one(
        set__user_name=current_user.name,
        set__ts=datetime.utcnow(),
        upsert=True,
    )
    return jsonify(ok=True)


@chat_bp.route('/api/typing')
@login_required
def api_typing_get():
    room_key = request.args.get('room', '')
    uid      = str(current_user.id)
    cutoff   = datetime.utcnow() - timedelta(seconds=4)
    typers   = [
        t.user_name
        for t in ChatTyping.objects(room=room_key, ts__gte=cutoff)
        if t.user_id != uid
    ]
    return jsonify(typers=typers)


# ── API: edit ─────────────────────────────────────────────────────────────────

@chat_bp.route('/api/edit/<msg_id>', methods=['POST'])
@login_required
def api_edit(msg_id):
    msg = ChatMessage.objects(id=msg_id).first()
    if not msg or msg.deleted:
        return jsonify(ok=False), 404
    if msg.user_id != str(current_user.id):
        return jsonify(ok=False), 403
    data     = request.get_json(force=True) or {}
    new_text = (data.get('text') or '').strip()[:4000]
    if not new_text:
        return jsonify(ok=False, error='empty'), 400
    msg.text   = new_text
    msg.edited = True
    msg.save()
    return jsonify(ok=True, text=new_text)


# ── API: forward ───────────────────────────────────────────────────────────────

@chat_bp.route('/api/forward', methods=['POST'])
@login_required
def api_forward():
    data        = request.get_json(force=True) or {}
    msg_id      = data.get('msg_id')
    target_room = data.get('target_room', 'group')
    receiver_id = data.get('receiver_id') or None

    orig = ChatMessage.objects(id=msg_id).first()
    if not orig or orig.deleted:
        return jsonify(ok=False), 404

    is_group = target_room == 'group' or target_room.startswith('ch_') or target_room.startswith('grp_')

    fwd = ChatMessage(
        user_id     =str(current_user.id),
        user_name   =current_user.name,
        user_role   =current_user.role,
        text        =orig.text or '',
        room        =target_room,
        receiver_id =receiver_id,
        read        =is_group,
        forwarded   =True,
        forward_from=orig.user_name,
        reactions   ={},
        readers     =[str(current_user.id)],
        file_data   =orig.file_data,
        file_name   =orig.file_name,
        file_type   =orig.file_type,
        file_size   =orig.file_size,
    )
    fwd.save()
    return jsonify(ok=True, message=fwd.to_dict())


# ── API: search inside conversation ───────────────────────────────────────────

@chat_bp.route('/api/search')
@login_required
def api_search():
    room_key = request.args.get('room', '')
    q        = request.args.get('q', '').strip()
    if not room_key or not q or len(q) < 2:
        return jsonify(results=[])

    import re as _re
    pattern = _re.compile(_re.escape(q), _re.IGNORECASE)
    msgs    = ChatMessage.objects(room=room_key, deleted=False).order_by('timestamp')
    results = [
        {'id': str(m.id), 'text': m.text or '', 'ts': m.timestamp.strftime('%d/%m %H:%M'), 'user': m.user_name}
        for m in msgs if m.text and pattern.search(m.text)
    ]
    return jsonify(results=results)


# ── API: inbox status (nav badge) ─────────────────────────────────────────────

@chat_bp.route('/api/inbox-status')
@login_required
def api_inbox_status():
    me_id  = str(current_user.id)
    result = {}
    users  = list(User.objects.only('id', 'last_seen').filter(id__ne=me_id))
    for u in users:
        uid      = str(u.id)
        room_key = _private_room(me_id, uid)
        unread   = ChatMessage.objects(room=room_key, receiver_id=me_id, read=False).count()
        result[uid] = {'unread': unread, 'online': _is_online(u)}

    total = sum(v['unread'] for v in result.values())
    return jsonify(users=result, total_unread=total)
