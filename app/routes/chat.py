import base64
import mimetypes
import re
from datetime import datetime, timedelta

from flask import (Blueprint, render_template, request, jsonify,
                   abort, redirect, url_for, flash, g)
from flask_login import login_required, current_user
from app import limiter

from app.models.chat_message import ChatMessage, _private_room
from app.models.chat_file    import ChatFile
from app.models.chat_group   import ChatGroup
from app.models.chat_typing  import ChatTyping
from app.models.user         import User

chat_bp = Blueprint('chat', __name__, url_prefix='/chat')


def _send_push_notifications(recipient_id: str, sender_name: str, text: str, room_key: str):
    """Send Web Push to all subscriptions of an offline user (background thread)."""
    import threading, json as _json, logging as _logging
    from flask import current_app

    _log = _logging.getLogger(__name__)

    # Capture config BEFORE the thread starts (app context only exists in request)
    priv_key = current_app.config.get('VAPID_PRIVATE_KEY', '')
    email    = current_app.config.get('VAPID_EMAIL', 'mailto:admin@netstock.app')

    def _push():
        try:
            from pywebpush import webpush, WebPushException
            recipient = User.objects(id=recipient_id).only('push_subscriptions', 'last_seen').first()
            if not recipient:
                _log.warning('push: recipient %s not found', recipient_id)
                return
            if not recipient.push_subscriptions:
                _log.warning('push: recipient %s has no subscriptions', recipient_id)
                return
            if _is_online(recipient):
                _log.warning('push: recipient %s is online — skipping', recipient_id)
                return  # already online — SocketIO handles it
            _log.warning('push: sending to offline recipient %s', recipient_id)

            payload = _json.dumps({
                'title': sender_name,
                'body':  (text or '')[:80],
                'icon':  '/static/img/logo.png',
                'url':   '/chat',
                'room':  room_key,
            })
            if not priv_key:
                _log.warning('push: VAPID_PRIVATE_KEY not configured')
                return

            dead = []
            for sub in recipient.push_subscriptions:
                try:
                    webpush(
                        subscription_info=sub,
                        data=payload,
                        vapid_private_key=priv_key,
                        vapid_claims={'sub': email},
                    )
                    _log.warning('push: sent to %s endpoint=%s', recipient_id, sub.get('endpoint', '')[:40])
                except WebPushException as e:
                    _log.warning('push: WebPushException for %s: %s', recipient_id, e)
                    if e.response and e.response.status_code in (404, 410):
                        dead.append(sub)
                except Exception as e:
                    _log.error('push: error for %s: %s', recipient_id, e)
            if dead:
                User.objects(id=recipient_id).update_one(
                    pull_all__push_subscriptions=dead
                )
        except Exception as e:
            _log.error('push: outer error: %s', e)

    threading.Thread(target=_push, daemon=True).start()

_MAX_HISTORY  = 40
_MAX_FILE_B   = 50 * 1024 * 1024  # 50 MB
_ONLINE_SECS  = 35   # online = active in last 35s (heartbeat every 20s + buffer)
_REACTIONS    = ['👍', '❤️', '🔥', '✅', '😂', '😮']

_CHANNELS = []  # predefined channels removed — only groups and DMs remain


def _can_access_room(user_id, room_key):
    """Return True if user_id is allowed to read/write this room."""
    if room_key == 'group' or room_key.startswith('ch_'):
        return True
    if room_key.startswith('grp_'):
        grp = ChatGroup.objects(id=room_key[4:]).first()
        return bool(grp and grp.is_member(user_id))
    if room_key.startswith('pm_'):
        # room key: pm_<uid1>_<uid2> — uids are 24-char hex, no underscores
        return user_id in room_key[3:].split('_')
    return False


def _is_online(user):
    if not user.last_seen:
        return False
    return (datetime.utcnow() - user.last_seen) < timedelta(seconds=_ONLINE_SECS)


def _file_type(mime):
    if mime and mime.startswith('image/'):
        return 'image'
    if mime and mime.startswith('audio/'):
        return 'audio'
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
    from app.utils.cache import cache as _cache
    me_id = str(current_user.id)
    _ck   = f'chat_app_{me_id}'
    _hit  = _cache.get(_ck)
    if _hit:
        return render_template('chat/app.html', **_hit)
    users  = [u for u in User.objects.only('id', 'name').order_by('name') if str(u.id) != me_id]
    groups = list(ChatGroup.objects(member_ids=me_id).order_by('name'))
    _ctx = dict(users=users, groups=groups, channels=_CHANNELS,
                reactions=_REACTIONS, me_id=me_id)
    _cache.set(_ck, _ctx, timeout=30)
    return render_template('chat/app.html', **_ctx)


@chat_bp.route('/groups')
@login_required
def groups():
    if not current_user.is_admin:
        abort(403)
    me_id     = str(current_user.id)
    all_groups = list(ChatGroup.objects.order_by('name'))
    all_users  = [u for u in User.objects.only('id', 'name').order_by('name') if str(u.id) != me_id]
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
    from app.utils.cache import cache as _cache
    me_id  = str(current_user.id)
    _ck = f'chat_convs_{me_id}'
    _hit = _cache.get(_ck)
    if _hit:
        return jsonify(_hit)
    pinned    = list(current_user.pinned_rooms    or [])
    favorites = list(current_user.favorite_rooms or [])

    # --- Build the full list of room keys we need last-messages for ---
    all_users   = [u for u in User.objects.only('id', 'name', 'last_seen', 'profile_photo').order_by('name') if str(u.id) != me_id]
    my_groups   = list(ChatGroup.objects(member_ids=me_id).order_by('name'))
    dm_keys     = [_private_room(me_id, str(u.id)) for u in all_users]
    grp_keys    = [g.room_key for g in my_groups]
    ch_keys     = [ch['key'] for ch in _CHANNELS] + ['group']
    all_keys    = ch_keys + grp_keys + dm_keys

    # Single aggregation: last message per room (replaces N individual .first() queries)
    last_msgs = {}
    if all_keys:
        pipeline = [
            {'$match':  {'room': {'$in': all_keys}}},
            {'$sort':   {'room': 1, 'timestamp': -1}},
            {'$group':  {'_id': '$room',
                         'text':      {'$first': '$text'},
                         'deleted':   {'$first': '$deleted'},
                         'timestamp': {'$first': '$timestamp'}}},
        ]
        for doc in ChatMessage._get_collection().aggregate(pipeline):
            last_msgs[doc['_id']] = doc

    # Unread DM counts for current user
    unread_map = {}
    if dm_keys:
        for doc in ChatMessage._get_collection().aggregate([
            {'$match': {'room': {'$in': dm_keys}, 'receiver_id': me_id, 'read': False}},
            {'$group': {'_id': '$room', 'count': {'$sum': 1}}},
        ]):
            unread_map[doc['_id']] = doc['count']

    # Group/channel unread counts — single aggregation (replaces N count_documents calls)
    try:
        from app.models.chat_last_read import ChatLastRead
        group_keys = grp_keys + ch_keys  # ch_keys already contains 'group'
        last_read_docs = {
            d.room: d.last_read_at
            for d in ChatLastRead.objects(user_id=me_id, room__in=group_keys)
        }
        group_unread_map = {}
        if last_read_docs:
            or_conds = [
                {'room': rk, 'timestamp': {'$gt': lr}}
                for rk, lr in last_read_docs.items()
            ]
            for doc in ChatMessage._get_collection().aggregate([
                {'$match': {'$or': or_conds, 'user_id': {'$ne': me_id}, 'deleted': {'$ne': True}}},
                {'$group': {'_id': '$room', 'count': {'$sum': 1}}},
            ]):
                group_unread_map[doc['_id']] = doc['count']
    except Exception:
        import traceback; traceback.print_exc()
        group_unread_map = {}

    def _last(rk):
        doc = last_msgs.get(rk)
        if not doc or doc.get('deleted'):
            return '', '', ''
        ts = doc['timestamp']
        display = ts.strftime('%H:%M') if ts else ''
        iso     = (ts.isoformat() + 'Z') if ts else ''
        return (doc.get('text') or '')[:60], display, iso

    result = []

    # 1. Everyone channel
    msg, ts, iso = _last('group')
    result.append({'type': 'channel', 'room': 'group', 'name': 'כולם', 'icon': 'bi-people',
                   'last_msg': msg, 'last_ts': ts, 'last_iso': iso,
                   'unread': group_unread_map.get('group', 0), 'online': None,
                   'pinned': 'group' in pinned, 'favorite': 'group' in favorites})

    # 2. Channels
    for ch in _CHANNELS:
        msg, ts, iso = _last(ch['key'])
        result.append({'type': 'channel', 'room': ch['key'], 'name': ch['name'], 'icon': ch['icon'],
                       'last_msg': msg, 'last_ts': ts, 'last_iso': iso,
                       'unread': group_unread_map.get(ch['key'], 0), 'online': None,
                       'pinned': ch['key'] in pinned, 'favorite': ch['key'] in favorites})

    # 3. Groups
    for grp in my_groups:
        rk = grp.room_key
        msg, ts, iso = _last(rk)
        result.append({'type': 'group', 'room': rk, 'name': grp.name, 'icon': 'bi-people-fill',
                       'last_msg': msg, 'last_ts': ts, 'last_iso': iso,
                       'unread': group_unread_map.get(rk, 0), 'online': None,
                       'member_count': len(grp.member_ids or []),
                       'pinned': rk in pinned, 'favorite': rk in favorites})

    # 4. Direct messages
    for u in all_users:
        rk = _private_room(me_id, str(u.id))
        msg, ts, iso = _last(rk)
        result.append({'type': 'dm', 'room': rk, 'name': u.name, 'role': u.role,
                       'user_id': str(u.id), 'icon': None,
                       'photo': u.profile_photo or '',
                       'last_msg': msg, 'last_ts': ts, 'last_iso': iso,
                       'unread': unread_map.get(rk, 0),
                       'online': _is_online(u),
                       'pinned': rk in pinned, 'favorite': rk in favorites})

    payload = dict(conversations=result, pinned=pinned, favorites=favorites)
    _cache.set(_ck, payload, timeout=15)
    return jsonify(payload)


# ── API: messages ──────────────────────────────────────────────────────────────

@chat_bp.route('/api/messages')
@login_required
def api_messages():
    room_key    = request.args.get('room', 'group')
    since       = request.args.get('since')
    receiver_id = request.args.get('receiver_id', '')

    # Access control — all room types
    if not _can_access_room(str(current_user.id), room_key):
        return jsonify(messages=[]), 403

    # For DMs: look up the other user's online status once
    recv_online = False
    if room_key.startswith('pm_') and receiver_id:
        other = User.objects(id=receiver_id).only('last_seen').first()
        if other:
            recv_online = _is_online(other)

    def _to_d(m):
        # receiver_online only relevant for messages sent by current user
        online = recv_online if m.user_id == str(current_user.id) else False
        return m.to_dict(receiver_online=online)

    qs = ChatMessage.objects(room=room_key)
    if since:
        try:
            qs = qs.filter(timestamp__gt=datetime.fromisoformat(since))
        except ValueError:
            pass
    else:
        qs = qs.order_by('-timestamp').limit(_MAX_HISTORY)
        qs = list(reversed(list(qs)))
        return jsonify(messages=[_to_d(m) for m in qs])

    messages = list(qs.order_by('timestamp').limit(50))

    # Mark PM messages as read when fetching
    if room_key.startswith('pm_'):
        ChatMessage.objects(
            room=room_key, receiver_id=str(current_user.id), read=False
        ).update(set__read=True, add_to_set__readers=str(current_user.id))

    # Piggyback typing indicators — free ride on existing poll, no extra HTTP request
    uid    = str(current_user.id)
    cutoff = datetime.utcnow() - timedelta(seconds=5)
    typers = [
        t.user_name
        for t in ChatTyping.objects(room=room_key, ts__gte=cutoff)
        if t.user_id != uid
    ]

    return jsonify(messages=[_to_d(m) for m in messages], typers=typers)


@chat_bp.route('/api/file/<msg_id>')
@login_required
def api_file(msg_id):
    """Serve file data — fetched separately to keep message queries lightweight."""
    msg = ChatMessage.objects(id=msg_id).only('file_id', 'file_name', 'file_type', 'room', 'deleted').first()
    if not msg or not msg.file_id or msg.deleted:
        abort(404)
    if not _can_access_room(str(current_user.id), msg.room or 'group'):
        abort(403)
    cf = ChatFile.objects(id=msg.file_id).first()
    if not cf:
        abort(404)
    return jsonify(file_data=cf.data, file_name=msg.file_name, file_type=msg.file_type)


# ── API: send ──────────────────────────────────────────────────────────────────

@chat_bp.route('/api/send', methods=['POST'])
@login_required
@limiter.limit('60 per minute')
def api_send():
    data        = request.get_json(force=True) or {}
    text        = (data.get('text') or '').strip()[:4000]
    room_key    = data.get('room', 'group')
    receiver_id = data.get('receiver_id') or None
    reply_to_id = data.get('reply_to_id') or None

    if not text:
        return jsonify(ok=False, error='empty'), 400

    # Access control — all room types
    if not _can_access_room(str(current_user.id), room_key):
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
    # Include receiver online status so sender sees correct tick immediately
    recv_online = False
    if receiver_id:
        other = User.objects(id=receiver_id).only('last_seen').first()
        if other:
            recv_online = _is_online(other)

    # Push real-time notification to recipients on other pages
    from app.routes.chat_socket import emit_chat_notify
    _rname = current_user.name if room_key.startswith('pm_') else (
        'כולם' if room_key == 'group' else room_key
    )
    if room_key.startswith('grp_'):
        grp_obj = ChatGroup.objects(id=room_key[4:]).first()
        _rname  = grp_obj.name if grp_obj else room_key
    emit_chat_notify(str(current_user.id), current_user.name, text, room_key, _rname)

    # Mention notifications — emit directly to each mentioned user's personal room
    import re as _re
    from app import socketio as _sio
    _mentioned = set(_re.findall(r'@(\S+)', text))
    if _mentioned:
        _me_id = str(current_user.id)
        for _mname in _mentioned:
            _u = User.objects(name=_mname).first()
            if _u and str(_u.id) != _me_id:
                _sio.emit('chat_notify', {
                    'sender':    current_user.name,
                    'sender_id': _me_id,
                    'text':      f'תויגת: {text[:80]}',
                    'room':      room_key,
                    'room_name': f'תיוג מ-{current_user.name}',
                }, to='notif_' + str(_u.id), namespace='/')

    # Web Push — notify offline recipient(s)
    if receiver_id:
        _send_push_notifications(receiver_id, current_user.name, text, room_key)
    elif room_key == 'group' or room_key.startswith('ch_') or room_key.startswith('grp_'):
        # Notify all offline members of the room
        import threading as _th
        def _push_group():
            try:
                me_id = str(current_user.id)
                if room_key.startswith('grp_'):
                    grp_obj2 = ChatGroup.objects(id=room_key[4:]).first()
                    member_ids = [str(m) for m in (grp_obj2.members if grp_obj2 else [])] if room_key.startswith('grp_') else []
                else:
                    cutoff = datetime.utcnow() - timedelta(seconds=_ONLINE_SECS)
                    member_ids = [
                        str(u.id) for u in User.objects(
                            last_seen__lt=cutoff,
                            push_subscriptions__exists=True,
                            push_subscriptions__0__exists=True,
                        ).only('id')
                    ]
                for uid in member_ids:
                    if uid != me_id:
                        _send_push_notifications(uid, current_user.name, text, room_key)
            except Exception:
                pass
        _th.Thread(target=_push_group, daemon=True).start()

    return jsonify(ok=True, message=msg.to_dict(receiver_online=recv_online))


@chat_bp.route('/api/push-subscribe', methods=['POST'])
@login_required
def api_push_subscribe():
    sub = request.get_json(force=True) or {}
    if not sub.get('endpoint'):
        return jsonify(ok=False), 400
    User.objects(id=current_user.id).update_one(
        add_to_set__push_subscriptions=sub
    )
    return jsonify(ok=True)


@chat_bp.route('/api/push-unsubscribe', methods=['POST'])
@login_required
def api_push_unsubscribe():
    sub = request.get_json(force=True) or {}
    if sub.get('endpoint'):
        User.objects(id=current_user.id).update_one(
            pull__push_subscriptions__endpoint=sub['endpoint']
        )
    return jsonify(ok=True)


@chat_bp.route('/api/push-status')
@login_required
def api_push_status():
    from flask import current_app
    u = User.objects(id=current_user.id).only('push_subscriptions').first()
    subs = u.push_subscriptions or [] if u else []
    return jsonify(
        subscriptions=len(subs),
        vapid_ok=bool(current_app.config.get('VAPID_PRIVATE_KEY')),
        vapid_pub=bool(current_app.config.get('VAPID_PUBLIC_KEY')),
    )


@chat_bp.route('/api/upload', methods=['POST'])
@login_required
@limiter.limit('20 per minute')
def api_upload():
    room_key    = request.form.get('room', 'group')
    receiver_id = request.form.get('receiver_id') or None
    reply_to_id = request.form.get('reply_to_id') or None
    caption     = (request.form.get('caption') or '').strip()[:500]

    # Access control — all room types
    if not _can_access_room(str(current_user.id), room_key):
        return jsonify(ok=False, error='forbidden'), 403

    f = request.files.get('file')
    if not f:
        return jsonify(ok=False, error='no file'), 400

    raw = f.read()
    if len(raw) > _MAX_FILE_B:
        return jsonify(ok=False, error='too_large'), 400

    mime    = f.content_type or mimetypes.guess_type(f.filename)[0] or 'application/octet-stream'
    ftype   = _file_type(mime)
    b64data = 'data:' + mime + ';base64,' + base64.b64encode(raw).decode()

    # Save file separately — keeps ChatMessage documents lightweight
    cf = ChatFile(data=b64data, name=f.filename, file_type=ftype, size=len(raw))
    cf.save()

    reply_text = reply_user = ''
    if reply_to_id:
        orig = ChatMessage.objects(id=reply_to_id).first()
        if orig and not orig.deleted:
            reply_text = (orig.text or '')[:200]
            reply_user = orig.user_name

    is_group_room = room_key == 'group' or room_key.startswith('ch_') or room_key.startswith('grp_')

    msg = ChatMessage(
        user_id      =str(current_user.id),
        user_name    =current_user.name,
        user_role    =current_user.role,
        text         =caption,
        room         =room_key,
        receiver_id  =receiver_id,
        read         =is_group_room,
        reply_to_id  =reply_to_id or '',
        reply_to_text=reply_text,
        reply_to_user=reply_user,
        file_id      =str(cf.id),
        file_name    =f.filename,
        file_type    =ftype,
        file_size    =len(raw),
        reactions    ={},
        readers      =[str(current_user.id)],
    )
    try:
        msg.save()
    except Exception:
        cf.delete()
        raise
    d = msg.to_dict()
    d['file_data'] = b64data   # send back to sender immediately (no extra fetch needed)
    return jsonify(ok=True, message=d)


# ── API: reactions ─────────────────────────────────────────────────────────────

@chat_bp.route('/api/react', methods=['POST'])
@login_required
@limiter.limit('60 per minute')
def api_react():
    data   = request.get_json(force=True) or {}
    msg_id = data.get('msg_id')
    emoji  = data.get('emoji')
    if not msg_id or emoji not in _REACTIONS:
        return jsonify(ok=False), 400

    msg = ChatMessage.objects(id=msg_id).first()
    if not msg:
        return jsonify(ok=False), 404
    if not _can_access_room(str(current_user.id), msg.room or 'group'):
        return jsonify(ok=False), 403

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
    file_id_to_clean = msg.file_id if msg.file_id else None
    msg.deleted = True
    msg.text    = ''
    msg.save()
    if file_id_to_clean:
        if ChatMessage.objects(file_id=file_id_to_clean, deleted=False).count() == 0:
            ChatFile.objects(id=file_id_to_clean).delete()
    return jsonify(ok=True)


# ── API: read receipt ──────────────────────────────────────────────────────────

@chat_bp.route('/api/read', methods=['POST'])
@login_required
def api_read():
    from app.models.chat_last_read import ChatLastRead
    data     = request.get_json(force=True) or {}
    room_key = data.get('room', '')
    uid      = str(current_user.id)
    if room_key.startswith('pm_'):
        ChatMessage.objects(
            room=room_key, receiver_id=uid, read=False
        ).update(set__read=True, add_to_set__readers=uid)
        # Always notify — even if 0 messages updated, sender's existing
        # checkmarks may still need updating (e.g. page reload after read)
        from app import socketio
        socketio.emit('chat_read', {'room': room_key, 'reader_id': uid},
                      to=room_key, namespace='/')
    elif room_key:
        ChatLastRead.objects(user_id=uid, room=room_key).update_one(
            set__last_read_at=datetime.utcnow(),
            upsert=True,
        )
    return jsonify(ok=True)


# ── API: pin / favorite ────────────────────────────────────────────────────────

@chat_bp.route('/api/pin', methods=['POST'])
@login_required
def api_pin():
    data     = request.get_json(force=True) or {}
    room_key = data.get('room', '')
    if room_key and not _can_access_room(str(current_user.id), room_key):
        return jsonify(ok=False, error='forbidden'), 403
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
    if room_key and not _can_access_room(str(current_user.id), room_key):
        return jsonify(ok=False, error='forbidden'), 403
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


# ── API: profile photo ─────────────────────────────────────────────────────────

@chat_bp.route('/api/profile-photo', methods=['POST'])
@login_required
def api_profile_photo():
    data  = request.get_json(force=True) or {}
    photo = (data.get('photo') or '').strip()
    uid   = str(current_user.id)
    from app.models.user import _user_cache
    from app.utils.cache import cache as _cache

    def _bust_all_conv_caches():
        # Invalidate conversation cache for every active user so they
        # immediately see the updated photo on their next poll.
        for cached_uid in list(_user_cache.keys()):
            _cache.delete(f'chat_convs_{cached_uid}')

    # Empty string = remove photo
    if photo == '':
        User.objects(id=uid).update_one(unset__profile_photo=1)
        current_user.profile_photo = None
        _user_cache.pop(uid, None)
        _bust_all_conv_caches()
        return jsonify(ok=True, removed=True)

    _ALLOWED_MIME = ('data:image/jpeg;', 'data:image/png;', 'data:image/gif;', 'data:image/webp;')
    if not any(photo.startswith(m) for m in _ALLOWED_MIME):
        return jsonify(ok=False, error='invalid'), 400
    if len(photo) > 250 * 1024:
        return jsonify(ok=False, error='too_large'), 400
    uid = str(current_user.id)
    User.objects(id=uid).update_one(set__profile_photo=photo)
    current_user.profile_photo = photo
    _user_cache.pop(uid, None)
    _bust_all_conv_caches()
    return jsonify(ok=True)


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
    me_id       = str(current_user.id)

    orig = ChatMessage.objects(id=msg_id).first()
    if not orig or orig.deleted:
        return jsonify(ok=False), 404

    # Must have read access to the source room and write access to the target room
    if not _can_access_room(me_id, orig.room or 'group'):
        return jsonify(ok=False), 403
    if not _can_access_room(me_id, target_room):
        return jsonify(ok=False), 403

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
        file_id     =orig.file_id or '',
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

    if not _can_access_room(str(current_user.id), room_key):
        return jsonify(results=[]), 403

    import re as _re
    msgs = ChatMessage.objects(
        room=room_key, deleted=False,
        text__icontains=q,
    ).order_by('timestamp').limit(100)
    results = [
        {'id': str(m.id), 'text': m.text or '', 'ts': m.timestamp.strftime('%d/%m %H:%M'), 'user': m.user_name}
        for m in msgs
    ]
    return jsonify(results=results)


# ── API: inbox status (nav badge) ─────────────────────────────────────────────

@chat_bp.route('/api/inbox-status')
@login_required
def api_inbox_status():
    me_id  = str(current_user.id)

    # One aggregation instead of N individual count() queries
    pipeline = [
        {'$match': {'receiver_id': me_id, 'read': False}},
        {'$group': {'_id': '$room', 'count': {'$sum': 1}}},
    ]
    unread_by_room = {
        doc['_id']: doc['count']
        for doc in ChatMessage._get_collection().aggregate(pipeline)
    }

    result = {}
    users  = list(User.objects.only('id', 'last_seen').filter(id__ne=me_id))
    for u in users:
        uid      = str(u.id)
        room_key = _private_room(me_id, uid)
        result[uid] = {
            'unread': unread_by_room.get(room_key, 0),
            'online': _is_online(u),
        }

    total = sum(v['unread'] for v in result.values())
    return jsonify(users=result, total_unread=total)
