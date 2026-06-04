/* NetStock Chat — Real-time WebSocket SPA */
(function () {
  'use strict';

  /* ── State ──────────────────────────────────────────────────────────────── */
  var S = {
    me:             window.CHAT_ME_ID   || '',
    meName:         window.CHAT_ME_NAME || '',
    meRole:         window.CHAT_ME_ROLE || '',
    csrf:           document.querySelector('meta[name=csrf-token]') ? document.querySelector('meta[name=csrf-token]').content : '',
    room:           null,
    roomName:       '',
    roomType:       '',
    receiverId:     '',
    replyTo:        null,
    lastTs:         null,
    typingTimer:    null,
    conversations:  [],
    pinned:         [],
    favorites:      [],
    theme:          localStorage.getItem('chat-theme') || 'light',
    reactions:      window.CHAT_REACTIONS || ['👍','❤️','🔥','✅','😂','😮'],
    searchQ:        '',
    soundMuted:     localStorage.getItem('chat-sound-muted') === '1',
    searchResults:  [],
    searchIdx:      -1,
    forwardMsgId:   null,
    socketReady:    false,   // WebSocket connected and authenticated
  };

  /* ── WebSocket (Socket.IO) ───────────────────────────────────────────────── */
  var _socket          = null;
  var _pendingConfirms = {};   // tmpId → fallback-timer handle

  function initSocket() {
    if (typeof io === 'undefined') return;  // socket.io not loaded

    _socket = io({
      transports: ['websocket', 'polling'],  // prefer WebSocket, fall back to polling
      reconnection:      true,
      reconnectionDelay: 1000,
      reconnectionAttempts: Infinity,
    });

    _socket.on('connect', function () {
      S.socketReady = true;
      // Re-join current room after reconnect
      if (S.room) _socket.emit('chat_join', { room: S.room });
    });

    _socket.on('disconnect', function () {
      S.socketReady = false;
    });

    // New message broadcast from server
    _socket.on('chat_message', function (msg) {
      // Always update sidebar preview (active room or not)
      _sidebarTick(msg.room, msg.text, msg._iso, msg.user_id !== S.me && msg.room !== S.room);

      if (!EL.messagesArea) return;

      // Skip if we already have this message (own optimistic or duplicate)
      if (EL.messagesArea.querySelector('[data-id="' + msg.id + '"]')) return;

      // Own message — the optimistic bubble is already showing; chat_confirmed upgrades it
      if (msg.user_id === S.me) return;

      // Message is for a different room — toast only
      if (msg.room !== S.room) { showToast(msg); return; }

      // Append instantly — no poll delay
      var area = EL.messagesArea;
      var atBottom = area.scrollHeight - area.scrollTop - area.clientHeight < 80;
      appendMessage(msg, true);
      if (S.lastTs === null || msg._iso > S.lastTs) S.lastTs = msg._iso;
      if (atBottom) scrollBottom();
      showToast(msg);
    });

    // Server confirms our optimistic message: tmp_id → real id
    _socket.on('chat_confirmed', function (data) {
      // Cancel the HTTP fallback timer for this message
      if (_pendingConfirms[data.tmp_id]) {
        clearTimeout(_pendingConfirms[data.tmp_id]);
        delete _pendingConfirms[data.tmp_id];
      }
      if (!EL.messagesArea) return;
      var el = EL.messagesArea.querySelector('[data-id="' + data.tmp_id + '"]');
      if (el) {
        el.setAttribute('data-id', data.real_id);
        el.style.opacity = '';
      }
      if (data._iso && (S.lastTs === null || data._iso > S.lastTs)) {
        S.lastTs = data._iso;
      }
    });

    // Typing indicator from others
    _socket.on('chat_typing', function (data) {
      if (!EL.typingBar || data.user_id === S.me) return;
      EL.typingBar.innerHTML =
        '<span style="font-size:.78rem;color:var(--chat-text-muted)">' +
        _esc(data.user) + ' מקליד...' +
        ' <span class="typing-dots"><span></span><span></span><span></span></span>' +
        '</span>';
      clearTimeout(_typingClearTimer);
      _typingClearTimer = setTimeout(function () {
        if (EL.typingBar) EL.typingBar.innerHTML = '';
      }, 4000);
    });
  }
  var _typingClearTimer = null;

  /* ── DOM refs ───────────────────────────────────────────────────────────── */
  var $ = function(sel, ctx) { return (ctx||document).querySelector(sel); };
  var $$ = function(sel, ctx) { return Array.from((ctx||document).querySelectorAll(sel)); };

  var EL = {};

  /* ── Init ───────────────────────────────────────────────────────────────── */
  function init() {
    EL.sidebar      = $('#chatSidebar');
    EL.main         = $('#chatMain');
    EL.searchInput  = $('#chatSearchInput');
    EL.convList     = $('#chatConvList');
    EL.messagesArea = $('#chatMessagesArea');
    EL.inputField   = $('#chatInputField');
    EL.sendBtn      = $('#chatSendBtn');
    EL.attachBtn    = $('#chatAttachBtn');
    EL.fileInput    = $('#chatFileInput');
    EL.replyBar     = $('#chatReplyBar');
    EL.typingBar    = $('#chatTypingBar');
    EL.headerName   = $('#chatHeaderName');
    EL.headerSub    = $('#chatHeaderSub');
    EL.headerAvatar = $('#chatHeaderAvatar');
    EL.toastCont    = $('#chatToastContainer');
    EL.lightbox     = $('#chatLightbox');
    EL.lightboxImg  = $('#chatLightboxImg');
    EL.contextMenu  = $('#chatContextMenu');
    EL.uploadProg   = $('#chatUploadProgress');
    EL.themeBtn           = $('#chatThemeBtn');
    EL.pinBtn             = $('#chatPinBtn');
    EL.favBtn             = $('#chatFavBtn');
    EL.searchGroups       = $('#chatSearchGroups');
    EL.mobilBack          = $('#chatMobileBack');
    EL.searchInConvBtn    = $('#chatSearchInConvBtn');
    EL.searchInConv       = $('#chatSearchInConv');
    EL.convSearchInput    = $('#chatConvSearchInput');
    EL.searchCount        = $('#chatSearchCount');
    EL.searchPrev         = $('#chatSearchPrev');
    EL.searchNext         = $('#chatSearchNext');
    EL.searchClose        = $('#chatSearchClose');
    EL.soundBtn           = $('#chatSoundBtn');
    EL.notifBtn           = $('#chatNotifBtn');
    EL.forwardOverlay     = $('#chatForwardOverlay');
    EL.voiceBtn           = $('#chatVoiceBtn');
    EL.voiceBar           = $('#chatVoiceBar');
    EL.voiceTimer         = $('#chatVoiceTimer');
    EL.voiceStop          = $('#chatVoiceStop');
    EL.voiceCancel        = $('#chatVoiceCancel');
    EL.forwardList        = $('#chatForwardList');
    EL.forwardClose       = $('#chatForwardClose');

    applyTheme(S.theme);
    updateSoundBtn();
    updateNotifBtn();

    // Load conversations
    loadConversations();

    // Event listeners
    bindEvents();

    // Check URL param
    var params = new URLSearchParams(window.location.search);
    if (params.get('room')) openRoom(params.get('room'));

    // WebSocket handles real-time messages — no pollMessages needed.
    // pollConversations updates sidebar (last message preview, unread counts).
    // pollMessages kept as safety net for when socket is disconnected.
    setInterval(function() { if (!S.socketReady) pollMessages(); }, 3000);
    setInterval(pollConversations, 20000);

    // Init WebSocket connection
    initSocket();
  }

  /* ── Theme ──────────────────────────────────────────────────────────────── */
  function applyTheme(t) {
    document.getElementById('chatApp').setAttribute('data-chat-theme', t === 'dark' ? 'dark' : '');
    S.theme = t;
    localStorage.setItem('chat-theme', t);
    if (EL.themeBtn) EL.themeBtn.innerHTML = t === 'dark'
      ? '<i class="bi bi-sun"></i>'
      : '<i class="bi bi-moon"></i>';
  }

  /* ── Conversations ──────────────────────────────────────────────────────── */
  function loadConversations() {
    fetch('/chat/api/conversations')
      .then(function(r){ return r.json(); })
      .then(function(d){
        S.conversations = d.conversations || [];
        S.pinned        = d.pinned        || [];
        S.favorites     = d.favorites     || [];
        renderSidebar();
      }).catch(function(){});
  }

  function pollConversations() {
    fetch('/chat/api/inbox-status')
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (!d.users) return;
        // Update unread badges + online dots in sidebar
        $$('.chat-conv-item[data-uid]').forEach(function(el){
          var uid  = el.dataset.uid;
          var info = d.users[uid];
          if (!info) return;
          var badge = el.querySelector('.chat-unread-badge');
          if (badge) {
            if (info.unread > 0) { badge.textContent = info.unread; badge.style.display = 'flex'; }
            else badge.style.display = 'none';
          }
          var dot = el.querySelector('.chat-online-dot');
          if (dot) dot.className = 'chat-online-dot' + (info.online ? ' online' : '');
        });
        // Update nav badge
        var navBadge = document.getElementById('chatUnreadBadge');
        if (navBadge) {
          if (d.total_unread > 0) { navBadge.textContent = d.total_unread; navBadge.classList.remove('d-none'); }
          else navBadge.classList.add('d-none');
        }
      }).catch(function(){});
  }

  function renderSidebar() {
    if (!EL.convList) return;
    var q      = S.searchQ.toLowerCase();
    var convs  = S.conversations.filter(function(c){
      return !q || c.name.toLowerCase().includes(q);
    });

    var pinned   = convs.filter(function(c){ return S.pinned.includes(c.room); });
    var favs     = convs.filter(function(c){ return S.favorites.includes(c.room) && !S.pinned.includes(c.room); });
    // "כולם" is the only channel — shown standalone at top, no section header
    var everyone = convs.filter(function(c){ return c.type === 'channel' && c.room === 'group' && !S.pinned.includes(c.room) && !S.favorites.includes(c.room); });
    var groups   = convs.filter(function(c){ return c.type === 'group' && !S.pinned.includes(c.room) && !S.favorites.includes(c.room); });
    var dms      = convs.filter(function(c){ return c.type === 'dm' && !S.pinned.includes(c.room) && !S.favorites.includes(c.room); });

    var html = '';

    if (pinned.length) {
      html += '<div class="chat-section-label"><i class="bi bi-pin-angle me-1"></i>מוצמד</div>';
      pinned.forEach(function(c){ html += convItem(c); });
    }

    if (favs.length) {
      html += '<div class="chat-section-label"><i class="bi bi-star me-1"></i>מועדפים</div>';
      favs.forEach(function(c){ html += convItem(c); });
    }

    // "כולם" — standalone, no section label
    everyone.forEach(function(c){ html += convItem(c); });

    if (groups.length) {
      html += '<div class="chat-section-label"><i class="bi bi-people me-1"></i>קבוצות</div>';
      groups.forEach(function(c){ html += convItem(c); });
    }

    if (dms.length) {
      html += '<div class="chat-section-label"><i class="bi bi-chat me-1"></i>שיחות</div>';
      dms.forEach(function(c){ html += convItem(c); });
    }

    if (!html) html = '<div class="text-center text-muted p-4" style="font-size:.85rem;">לא נמצא</div>';

    EL.convList.innerHTML = html;

    // Active
    $$('.chat-conv-item', EL.convList).forEach(function(el){
      if (el.dataset.room === S.room) el.classList.add('active');
      el.addEventListener('click', function(){ openRoom(el.dataset.room); });
    });
  }

  function convItem(c) {
    var isActive = c.room === S.room ? ' active' : '';
    var pinIcon  = S.pinned.includes(c.room) ? '<i class="bi bi-pin-angle-fill chat-pin-icon ms-1"></i>' : '';
    var unread   = c.unread > 0 ? '<div class="chat-unread-badge">' + c.unread + '</div>' : '';

    var avatar = '';
    if (c.type === 'dm') {
      avatar = '<div class="chat-conv-avatar">' +
        roleAvatar(c.role, 'sm') +
        '<span class="chat-online-dot' + (c.online ? ' online' : '') + '"></span>' +
        '</div>';
    } else {
      var icon = c.icon || 'bi-chat';
      avatar = '<div class="chat-conv-avatar">' +
        '<div class="role-avatar-sm role-admin"><i class="bi ' + icon + '"></i></div>' +
        '</div>';
    }

    var uidAttr = c.type === 'dm' ? ' data-uid="' + _esc(c.user_id) + '"' : '';

    return '<div class="chat-conv-item' + isActive + '" data-room="' + _esc(c.room) + '"' + uidAttr + '>' +
      avatar +
      '<div class="chat-conv-info">' +
        '<div class="chat-conv-name">' + _esc(c.name) + pinIcon + '</div>' +
        '<div class="chat-conv-preview">' + _esc(c.last_msg || '') + '</div>' +
      '</div>' +
      '<div class="chat-conv-meta">' +
        '<div class="chat-conv-time">' + _esc(c.last_ts || '') + '</div>' +
        unread +
      '</div>' +
    '</div>';
  }

  /* ── Open room ──────────────────────────────────────────────────────────── */
  function openRoom(roomKey) {
    // Leave previous room so stale broadcasts stop arriving
    if (_socket && S.socketReady && S.room && S.room !== roomKey) {
      _socket.emit('chat_leave', { room: S.room });
    }

    S.room      = roomKey;
    S.lastTs    = null;
    S.replyTo   = null;

    var conv = S.conversations.find(function(c){ return c.room === roomKey; });
    if (conv) {
      S.roomName   = conv.name;
      S.roomType   = conv.type;
      S.receiverId = conv.type === 'dm' ? (conv.user_id || '') : '';
    }

    // Update URL
    var url = new URL(window.location.href);
    url.searchParams.set('room', roomKey);
    history.replaceState({}, '', url.toString());

    // Join room via WebSocket so server pushes messages in real-time
    if (_socket && S.socketReady) {
      _socket.emit('chat_join', { room: roomKey });
    }

    // Mark as read immediately
    if (roomKey.startsWith('pm_')) {
      apiPost('/chat/api/read', {room: roomKey}).catch(function(){});
    }

    closeSearch();
    renderChatWindow();
    loadMessages();
    closeReplyBar();

    // Sidebar active
    $$('.chat-conv-item').forEach(function(el){
      el.classList.toggle('active', el.dataset.room === roomKey);
    });

    // Mobile: hide sidebar
    if (window.innerWidth < 768 && EL.sidebar) {
      EL.sidebar.classList.remove('mobile-open');
    }
  }

  /* ── Chat window ────────────────────────────────────────────────────────── */
  function renderChatWindow() {
    var conv = S.conversations.find(function(c){ return c.room === S.room; });

    // Header
    if (EL.headerName) EL.headerName.textContent = S.roomName;
    if (EL.headerSub)  EL.headerSub.textContent  = '';
    if (EL.headerAvatar && conv) {
      if (conv.type === 'dm') {
        EL.headerAvatar.innerHTML = '<div class="position-relative">' +
          roleAvatar(conv.role, '') +
          '<span class="chat-online-dot' + (conv.online ? ' online' : '') + '" style="position:absolute;bottom:0;right:0;border-color:var(--chat-header-bg);"></span>' +
          '</div>';
      } else {
        var icon = conv.icon || 'bi-chat';
        EL.headerAvatar.innerHTML = '<div class="role-avatar role-admin"><i class="bi ' + (icon) + '"></i></div>';
      }
    }

    // Show header + input
    $$('.chat-hidden-until-room').forEach(function(el){ el.style.display = ''; });
    var emptyState = $('#chatEmptyState');
    if (emptyState) emptyState.style.display = 'none';

    // Pin/fav button state
    if (EL.pinBtn) EL.pinBtn.title = S.pinned.includes(S.room) ? 'בטל הצמדה' : 'הצמד';
    if (EL.favBtn) EL.favBtn.title = S.favorites.includes(S.room) ? 'הסר ממועדפים' : 'הוסף למועדפים';
  }

  /* ── Messages ───────────────────────────────────────────────────────────── */
  function loadMessages() {
    if (!S.room || !EL.messagesArea) return;
    fetch('/chat/api/messages?room=' + encodeURIComponent(S.room))
      .then(function(r){ return r.json(); })
      .then(function(d){
        EL.messagesArea.innerHTML = '';
        var msgs = d.messages || [];
        var lastDate = '';
        msgs.forEach(function(msg){
          var d = msg.date || '';
          if (d !== lastDate) {
            appendDateDivider(d);
            lastDate = d;
          }
          appendMessage(msg, false);
        });
        if (msgs.length) S.lastTs = msgs[msgs.length - 1]._iso;
        scrollBottom();
      }).catch(function(){});
  }

  function pollMessages() {
    if (!S.room) return;
    var url = '/chat/api/messages?room=' + encodeURIComponent(S.room);
    if (S.lastTs) url += '&since=' + encodeURIComponent(S.lastTs);
    if (!S.lastTs) return;
    if (S.receiverId) url += '&receiver_id=' + encodeURIComponent(S.receiverId);

    fetch(url)
      .then(function(r){ return r.json(); })
      .then(function(d){
        var msgs = d.messages || [];
        if (!msgs.length) return;
        var area = EL.messagesArea;
        if (!area) return;
        var atBottom = area.scrollHeight - area.scrollTop - area.clientHeight < 80;
        var lastDate = '';
        // Get last date from existing messages
        var lastDiv = area.querySelector('.chat-date-divider:last-of-type');
        // Append new — deduplicate against real IDs AND optimistic tmp_* elements
        msgs.forEach(function(msg){
          if (area.querySelector('[data-id="' + msg.id + '"]')) return;
          // If this is my own message and there's a matching optimistic bubble,
          // upgrade the tmp ID instead of appending a duplicate
          if (msg.user_id === S.me) {
            var tmpEls = Array.from(area.querySelectorAll('[data-id^="tmp_"]'));
            var matched = tmpEls.find(function(el){
              var bubble = el.querySelector('.chat-bubble-text');
              return bubble && bubble.textContent.trim() === (msg.text || '').trim();
            });
            if (matched) {
              matched.setAttribute('data-id', msg.id);
              matched.style.opacity = '';
              if (S.lastTs === null || msg._iso > S.lastTs) S.lastTs = msg._iso;
              return;
            }
          }
          var d = msg.date || '';
          if (d !== lastDate) { appendDateDivider(d); lastDate = d; }
          appendMessage(msg, true);
          if (msg.user_id !== S.me) showToast(msg);
        });
        S.lastTs = msgs[msgs.length - 1]._iso;
        if (atBottom) scrollBottom();
      }).catch(function(){});
  }

  function pollTyping() {
    if (!S.room || !EL.typingBar) return;
    fetch('/chat/api/typing?room=' + encodeURIComponent(S.room))
      .then(function(r){ return r.json(); })
      .then(function(d){
        var typers = d.typers || [];
        if (!typers.length) {
          EL.typingBar.innerHTML = '';
        } else {
          EL.typingBar.innerHTML =
            '<span style="font-size:.78rem;color:var(--chat-text-muted)">' +
            _esc(typers.join(', ')) + ' מקליד...' +
            ' <span class="typing-dots"><span></span><span></span><span></span></span>' +
            '</span>';
        }
      }).catch(function(){});
  }

  // Update sidebar preview + unread badge without a full re-render
  function _sidebarTick(roomKey, text, iso, isUnread) {
    var conv = S.conversations.find(function(c){ return c.room === roomKey; });
    if (conv) {
      conv.last_msg = (text || '').slice(0, 60);
      if (iso) {
        var d = new Date(iso);
        conv.last_ts = String(d.getHours()).padStart(2,'0') + ':' + String(d.getMinutes()).padStart(2,'0');
      }
      if (isUnread) conv.unread = (conv.unread || 0) + 1;
    }
    if (!EL.convList) return;
    var item = EL.convList.querySelector('[data-room="' + roomKey + '"]');
    if (!item) return;
    var preview = item.querySelector('.chat-conv-preview');
    if (preview) preview.textContent = (text || '').slice(0, 60);
    if (iso) {
      var d = new Date(iso);
      var timeEl = item.querySelector('.chat-conv-time');
      if (timeEl) timeEl.textContent = String(d.getHours()).padStart(2,'0') + ':' + String(d.getMinutes()).padStart(2,'0');
    }
    if (isUnread && conv) {
      var badge = item.querySelector('.chat-unread-badge');
      if (badge) { badge.textContent = conv.unread; badge.style.display = 'flex'; }
    }
  }

  function appendDateDivider(dateStr) {
    var d = document.createElement('div');
    d.className = 'chat-date-divider';
    d.innerHTML = '<span>' + _esc(dateStr) + '</span>';
    EL.messagesArea.appendChild(d);
  }

  function appendMessage(msg, animate) {
    var isMe = msg.user_id === S.me;
    var row  = document.createElement('div');
    row.className = 'chat-msg-row ' + (isMe ? 'out' : 'in');
    row.dataset.id = msg.id;
    if (!animate) row.style.animation = 'none';
    row.innerHTML = buildBubbleHTML(msg, isMe);
    EL.messagesArea.appendChild(row);

    // Context menu on right-click
    row.addEventListener('contextmenu', function(e){
      e.preventDefault();
      showContextMenu(e, msg, isMe);
    });

    // Long-press for mobile
    var pressTimer;
    row.addEventListener('touchstart', function(e){
      pressTimer = setTimeout(function(){ showContextMenu(e.touches[0], msg, isMe); }, 500);
    });
    row.addEventListener('touchend', function(){ clearTimeout(pressTimer); });

    // Reaction picker toggle
    var reactionTrigger = row.querySelector('.chat-reaction-trigger');
    if (reactionTrigger) {
      reactionTrigger.addEventListener('click', function(e){
        e.stopPropagation();
        var picker = row.querySelector('.chat-reaction-picker');
        if (picker) picker.classList.toggle('show');
      });
    }

    // Reaction pill clicks
    row.querySelectorAll('.chat-reaction-picker span').forEach(function(el){
      el.addEventListener('click', function(e){
        e.stopPropagation();
        var picker = el.closest('.chat-reaction-picker');
        if (picker) picker.classList.remove('show');
        sendReaction(msg.id, el.textContent);
      });
    });

    // Existing reaction pill clicks
    row.querySelectorAll('.chat-reaction-pill').forEach(function(el){
      el.addEventListener('click', function(e){
        e.stopPropagation();
        sendReaction(msg.id, el.dataset.emoji);
      });
    });

    // Image lightbox
    var img = row.querySelector('.chat-file-preview img');
    if (img) {
      img.addEventListener('click', function(){
        if (EL.lightbox && EL.lightboxImg) {
          EL.lightboxImg.src = img.src;
          EL.lightbox.classList.add('show');
        }
      });
    }
  }

  function buildBubbleHTML(msg, isMe) {
    var avatar = !isMe ? '<div class="chat-msg-avatar">' + roleAvatar(msg.user_role, 'sm') + '</div>' : '';

    var senderName = (!isMe && (S.roomType === 'channel' || S.roomType === 'group' || S.room === 'group'))
      ? '<div class="chat-sender-name">' + _esc(msg.user_name) + '</div>' : '';

    var forwardHTML = '';
    if (msg.forwarded && !msg.deleted) {
      forwardHTML = '<div class="chat-forward-banner"><i class="bi bi-forward-fill"></i>הועבר מ-' + _esc(msg.forward_from || '') + '</div>';
    }

    var replyHTML = '';
    if (msg.reply_to_id && msg.reply_to_text) {
      replyHTML = '<div class="chat-reply-quote" data-jump="' + _esc(msg.reply_to_id) + '">' +
        '<div class="reply-user">' + _esc(msg.reply_to_user || '') + '</div>' +
        '<div class="reply-text">' + _esc(msg.reply_to_text) + '</div>' +
        '</div>';
    }

    var textHTML = '';
    if (!msg.deleted) {
      var rawText = _esc(msg.text || '');
      rawText = rawText.replace(/@(\S+)/g, '<span class="chat-mention">@$1</span>');
      textHTML = '<div class="chat-bubble-text">' + rawText + '</div>';
    }

    var fileHTML = '';
    if (msg.has_file && !msg.deleted) {
      if (msg.file_type === 'image') {
        fileHTML = '<div class="chat-file-preview">' +
          '<img src="" data-msg-id="' + _esc(msg.id) + '" alt="' + _esc(msg.file_name) + '" ' +
          'style="max-width:220px;border-radius:6px;cursor:pointer;" loading="lazy">' +
          '</div>';
      } else if (msg.file_type === 'audio') {
        fileHTML = '<div class="cap" data-msg-id="' + _esc(msg.id) + '">' +
          '<button class="cap-btn" type="button" aria-label="נגן"><i class="bi bi-play-fill"></i></button>' +
          '<div class="cap-body">' +
            '<div class="cap-wave">' + _genWaveBars(msg.id) + '</div>' +
            '<span class="cap-time">0:00</span>' +
          '</div>' +
          '</div>';
      } else {
        var icon = msg.file_type === 'pdf' ? 'bi-file-pdf' : msg.file_type === 'excel' ? 'bi-file-earmark-excel' : 'bi-file-earmark';
        fileHTML = '<a class="chat-file-btn" href="#" data-msg-id="' + _esc(msg.id) + '">' +
          '<i class="bi ' + icon + '"></i>' +
          _esc(msg.file_name || 'קובץ') +
          '</a>';
      }
    }

    var reactionsHTML = buildReactionsHTML(msg);

    var editedHTML = (msg.edited && !msg.deleted) ? '<span class="chat-edited-label">ערוך</span>' : '';

    var checks = '';
    if (isMe && !msg.deleted) {
      var read      = msg.readers && msg.readers.length > 1;  // receiver is in readers
      var delivered = !read && msg.receiver_online;           // online but not read yet
      var cls = read ? ' seen' : (delivered ? ' delivered' : '');
      var icon = (read || delivered) ? 'bi-check-all' : 'bi-check';
      checks = '<span class="chat-check' + cls + '"><i class="bi ' + icon + '"></i></span>';
    }

    var picker = '<div class="chat-reaction-picker">' +
      S.reactions.map(function(r){ return '<span>' + r + '</span>'; }).join('') +
      '</div>';

    var bubbleCls = 'chat-bubble' + (msg.deleted ? ' deleted' : '');

    return (avatar || '') +
      '<div class="chat-msg-body">' +
        senderName +
        '<div class="' + bubbleCls + '" style="position:relative;">' +
          picker +
          forwardHTML +
          replyHTML +
          textHTML +
          fileHTML +
          '<div class="chat-bubble-footer">' +
            editedHTML +
            '<span>' + _esc(msg.timestamp) + '</span>' +
            checks +
          '</div>' +
        '</div>' +
        reactionsHTML +
      '</div>';
  }

  function buildReactionsHTML(msg) {
    if (!msg.reactions || !Object.keys(msg.reactions).length) return '';
    var html = '<div class="chat-reactions">';
    Object.keys(msg.reactions).forEach(function(emoji){
      var users = msg.reactions[emoji] || [];
      if (!users.length) return;
      var mine = users.includes(S.me);
      html += '<span class="chat-reaction-pill' + (mine ? ' mine' : '') + '" data-emoji="' + _esc(emoji) + '">' +
        emoji + ' ' + users.length + '</span>';
    });
    html += '</div>';
    return html;
  }

  // Generate consistent waveform bars from message id
  function _genWaveBars(msgId) {
    var html = '', seed = 0;
    for (var c = 0; c < msgId.length; c++) seed = (seed * 31 + msgId.charCodeAt(c)) & 0xffff;
    for (var i = 0; i < 28; i++) {
      seed = (seed * 1103515245 + 12345) & 0x7fffffff;
      var h = 4 + (seed % 18);
      html += '<div class="cap-bar" style="height:' + h + 'px"></div>';
    }
    return html;
  }

  function _fetchFile(el, msgId) {
    fetch('/chat/api/file/' + msgId)
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (!d.file_data) return;
        if (el.tagName === 'IMG') el.src = d.file_data;
        else if (el.tagName === 'A') { el.href = d.file_data; el.download = d.file_name || 'file'; }
      }).catch(function(){});
  }

  // Lazy-load file data: images via IntersectionObserver, audio via custom player
  function lazyLoadFiles() {
    // ── Custom voice player (.cap) ───────────────────────────────────────────
    $$('.cap[data-msg-id]:not([data-loaded])').forEach(function(cap) {
      var msgId = cap.dataset.msgId;
      cap.dataset.loaded = '1';
      var btn   = cap.querySelector('.cap-btn');
      var timeEl = cap.querySelector('.cap-time');
      var bars  = Array.from(cap.querySelectorAll('.cap-bar'));
      var audio = new Audio();
      var loaded = false;

      function _fmt(s) {
        return Math.floor(s / 60) + ':' + String(Math.floor(s % 60)).padStart(2, '0');
      }
      function _setPct(pct) {
        var active = Math.floor(pct * bars.length);
        bars.forEach(function(b, i) { b.classList.toggle('active', i < active); });
      }

      btn.addEventListener('click', function() {
        if (!loaded) {
          btn.innerHTML = '<i class="bi bi-hourglass-split" style="font-size:.8rem"></i>';
          fetch('/chat/api/file/' + msgId)
            .then(function(r) { return r.json(); })
            .then(function(d) {
              if (!d.file_data) return;
              audio.src = d.file_data;
              loaded = true;
              audio.play().catch(function(){});
            }).catch(function() {
              btn.innerHTML = '<i class="bi bi-play-fill"></i>';
            });
        } else if (audio.paused) {
          audio.play().catch(function(){});
        } else {
          audio.pause();
        }
      });

      audio.addEventListener('play',  function() { btn.innerHTML = '<i class="bi bi-pause-fill"></i>'; });
      audio.addEventListener('pause', function() { btn.innerHTML = '<i class="bi bi-play-fill"></i>'; });
      audio.addEventListener('ended', function() {
        btn.innerHTML = '<i class="bi bi-play-fill"></i>';
        _setPct(0);
        if (audio.duration) timeEl.textContent = _fmt(audio.duration);
        audio.currentTime = 0;
      });
      audio.addEventListener('loadedmetadata', function() {
        timeEl.textContent = _fmt(audio.duration);
      });
      audio.addEventListener('timeupdate', function() {
        if (!audio.duration) return;
        _setPct(audio.currentTime / audio.duration);
        timeEl.textContent = _fmt(audio.currentTime);
      });

      // Click on waveform to seek
      cap.querySelector('.cap-wave').addEventListener('click', function(e) {
        if (!loaded || !audio.duration) return;
        var rect = this.getBoundingClientRect();
        audio.currentTime = ((e.clientX - rect.left) / rect.width) * audio.duration;
      });
    });

    // ── Images & file links ──────────────────────────────────────────────────
    $$('[data-msg-id]:not([data-loaded]):not(.cap)').forEach(function(el){
      var msgId = el.dataset.msgId;
      if (!msgId) return;
      el.dataset.loaded = '1';

      if ('IntersectionObserver' in window) {
        var obs = new IntersectionObserver(function(entries, o) {
          if (!entries[0].isIntersecting) return;
          o.disconnect();
          _fetchFile(el, msgId);
        }, { rootMargin: '200px' });
        obs.observe(el);
      } else {
        _fetchFile(el, msgId);
      }
    });
  }

  /* ── Send ───────────────────────────────────────────────────────────────── */
  function sendMessage() {
    // If recording — blue send button / Enter sends the recording
    if (_vRecording) { stopVoiceRecord(); return; }
    if (!EL.inputField || !S.room) return;
    var text = EL.inputField.value.trim();
    if (!text) return;

    // 1. Clear input immediately — zero input lag
    EL.inputField.value = '';
    autoResizeInput();

    // 2. Build optimistic message — appears NOW, before server responds
    var tmpId = 'tmp_' + Date.now();
    var now   = new Date();
    var hh = String(now.getHours()).padStart(2, '0');
    var mm = String(now.getMinutes()).padStart(2, '0');
    var optimistic = {
      id:            tmpId,
      _iso:          now.toISOString(),
      user_id:       S.me,
      user_name:     S.meName,
      user_role:     S.meRole,
      text:          text,
      timestamp:     hh + ':' + mm,
      date:          now.toLocaleDateString('he-IL'),
      reactions:     {},
      deleted:       false,
      edited:        false,
      has_file:      false,
      readers:       [],
      forwarded:     false,
      reply_to_id:   S.replyTo ? S.replyTo.id   : null,
      reply_to_text: S.replyTo ? S.replyTo.text  : null,
      reply_to_user: S.replyTo ? S.replyTo.user  : null,
    };

    var replySnapshot = S.replyTo;
    closeReplyBar();
    appendMessage(optimistic, true);

    // Mark as "sending" — subtle opacity until confirmed
    var tmpEl = EL.messagesArea.querySelector('[data-id="' + tmpId + '"]');
    if (tmpEl) tmpEl.style.opacity = '0.6';

    scrollBottom();

    var payload = { tmp_id: tmpId, text: text, room: S.room };
    if (S.receiverId)  payload.receiver_id = S.receiverId;
    if (replySnapshot) payload.reply_to_id = replySnapshot.id;

    if (_socket && S.socketReady) {
      // WebSocket path — confirmation handled by persistent chat_confirmed handler
      _socket.emit('chat_send', payload);
      // Fallback: if socket confirmation doesn't arrive within 5s, try HTTP
      _pendingConfirms[tmpId] = setTimeout(function () {
        delete _pendingConfirms[tmpId];
        var el = EL.messagesArea && EL.messagesArea.querySelector('[data-id="' + tmpId + '"]');
        if (el && el.getAttribute('data-id') === tmpId) {
          _sendViaHttp(tmpId, text, payload);
        }
      }, 5000);
    } else {
      _sendViaHttp(tmpId, text, payload);
    }
  }

  function _sendViaHttp(tmpId, text, payload) {
    var httpPayload = { text: payload.text, room: payload.room };
    if (payload.receiver_id) httpPayload.receiver_id = payload.receiver_id;
    if (payload.reply_to_id) httpPayload.reply_to_id = payload.reply_to_id;

    apiPost('/chat/api/send', httpPayload)
      .then(function(d) {
        var el = EL.messagesArea && EL.messagesArea.querySelector('[data-id="' + tmpId + '"]');
        if (d.ok && d.message) {
          if (el) { el.setAttribute('data-id', d.message.id); el.style.opacity = ''; }
          if (S.lastTs === null || d.message._iso > S.lastTs) S.lastTs = d.message._iso;
        } else {
          if (el) el.remove();
          if (EL.inputField) { EL.inputField.value = text; autoResizeInput(); }
        }
      })
      .catch(function() {
        var el = EL.messagesArea && EL.messagesArea.querySelector('[data-id="' + tmpId + '"]');
        if (el) el.remove();
        if (EL.inputField) { EL.inputField.value = text; autoResizeInput(); }
      });
  }

  /* ── File upload ────────────────────────────────────────────────────────── */
  function uploadFile(file) {
    if (!file || !S.room) return;
    if (file.size > 2 * 1024 * 1024) { alert('הקובץ גדול מדי (מקסימום 2MB)'); return; }

    if (EL.uploadProg) EL.uploadProg.classList.add('show');

    var fd = new FormData();
    fd.append('file', file);
    fd.append('room', S.room);
    if (S.receiverId) fd.append('receiver_id', S.receiverId);
    if (S.replyTo) fd.append('reply_to_id', S.replyTo.id);
    if (EL.inputField && EL.inputField.value.trim()) {
      fd.append('caption', EL.inputField.value.trim());
      EL.inputField.value = '';
    }

    fetch('/chat/api/upload', {
      method: 'POST',
      headers: { 'X-CSRFToken': S.csrf },
      body: fd,
    })
    .then(function(r){ return r.json(); })
    .then(function(d){
      if (EL.uploadProg) EL.uploadProg.classList.remove('show');
      if (d.ok && d.message) {
        appendMessage(d.message, true);
        if (S.lastTs === null || d.message._iso > S.lastTs) S.lastTs = d.message._iso;
        scrollBottom();
        closeReplyBar();
        // Trigger lazy load for the new image
        setTimeout(lazyLoadFiles, 100);
      }
    }).catch(function(){
      if (EL.uploadProg) EL.uploadProg.classList.remove('show');
    });
  }

  /* ── Reactions ──────────────────────────────────────────────────────────── */
  function sendReaction(msgId, emoji) {
    apiPost('/chat/api/react', {msg_id: msgId, emoji: emoji})
      .then(function(d){
        if (!d.ok) return;
        var row = EL.messagesArea && EL.messagesArea.querySelector('[data-id="' + msgId + '"]');
        if (!row) return;
        // Rebuild reactions area
        var existing = row.querySelector('.chat-reactions');
        var newHtml = buildReactionsHTML({reactions: d.reactions});
        if (existing) {
          existing.outerHTML = newHtml;
        } else if (newHtml) {
          var body = row.querySelector('.chat-msg-body');
          if (body) body.insertAdjacentHTML('beforeend', newHtml);
        }
        // Re-bind reaction pill clicks
        row.querySelectorAll('.chat-reaction-pill').forEach(function(el){
          el.onclick = null;
          el.addEventListener('click', function(e){
            e.stopPropagation();
            sendReaction(msgId, el.dataset.emoji);
          });
        });
      });
  }

  /* ── Context menu ───────────────────────────────────────────────────────── */
  function showContextMenu(e, msg, isMe) {
    if (!EL.contextMenu) return;
    EL.contextMenu.innerHTML = '';

    var items = [];
    if (!msg.deleted) {
      items.push({icon:'bi-reply',   label:'Reply',   fn: function(){ setReply(msg); }});
      items.push({icon:'bi-forward', label:'Forward', fn: function(){ openForwardModal(msg); }});
      items.push({icon:'bi-clipboard', label:'Copy', fn: function(){ navigator.clipboard && navigator.clipboard.writeText(msg.text||''); }});
    }
    if (isMe && !msg.deleted) {
      items.push({icon:'bi-pencil', label:'Edit', fn: function(){
        var row = EL.messagesArea && EL.messagesArea.querySelector('[data-id="' + msg.id + '"]');
        if (row) startEditMessage(row, msg);
      }});
      items.push({icon:'bi-trash',  label:'Delete', cls:'danger', fn: function(){ deleteMsg(msg.id); }});
    }

    items.forEach(function(item){
      var div = document.createElement('div');
      div.className = 'chat-context-item' + (item.cls ? ' ' + item.cls : '');
      div.innerHTML = '<i class="bi ' + item.icon + '"></i>' + item.label;
      div.addEventListener('click', function(){ item.fn(); EL.contextMenu.classList.remove('show'); });
      EL.contextMenu.appendChild(div);
    });

    EL.contextMenu.style.left  = Math.min(e.clientX, window.innerWidth - 180) + 'px';
    EL.contextMenu.style.top   = Math.min(e.clientY, window.innerHeight - items.length * 40) + 'px';
    EL.contextMenu.classList.add('show');
  }

  function deleteMsg(msgId) {
    apiPost('/chat/api/delete/' + msgId, {})
      .then(function(d){
        if (!d.ok) return;
        var row = EL.messagesArea && EL.messagesArea.querySelector('[data-id="' + msgId + '"]');
        if (row) {
          var bubble = row.querySelector('.chat-bubble');
          if (bubble) { bubble.classList.add('deleted'); bubble.querySelector('.chat-bubble-text') && (bubble.querySelector('.chat-bubble-text').textContent = '[הודעה נמחקה]'); }
        }
      });
  }

  /* ── Reply ──────────────────────────────────────────────────────────────── */
  function setReply(msg) {
    S.replyTo = {id: msg.id, text: msg.text || '', user: msg.user_name};
    if (EL.replyBar) {
      EL.replyBar.querySelector('.reply-user').textContent = msg.user_name;
      EL.replyBar.querySelector('.reply-text').textContent = msg.text || '';
      EL.replyBar.classList.add('show');
    }
    if (EL.inputField) EL.inputField.focus();
  }

  function closeReplyBar() {
    S.replyTo = null;
    if (EL.replyBar) EL.replyBar.classList.remove('show');
  }

  /* ── Typing ─────────────────────────────────────────────────────────────── */
  function onTyping() {
    if (!S.room) return;
    clearTimeout(S.typingTimer);
    if (_socket && S.socketReady) {
      _socket.emit('chat_typing', { room: S.room });
    } else {
      apiPost('/chat/api/typing', {room: S.room}).catch(function(){});
    }
    S.typingTimer = setTimeout(function(){}, 3000);
  }

  /* ── Toast ──────────────────────────────────────────────────────────────── */
  function showToast(msg) {
    if (msg.room === S.room) return;   // never notify for the room the user is already in
    if (!EL.toastCont) return;
    // Sound + browser notification for messages from others
    if (msg.user_id !== S.me) {
      playPing();
      showBrowserNotification(msg);
    }
    if (document.hidden) return;       // tab hidden — browser notification is enough

    var toast = document.createElement('div');
    toast.className = 'chat-toast';
    toast.innerHTML = '<div class="chat-toast-name">' + _esc(msg.user_name) + '</div>' +
      '<div class="chat-toast-text">' + _esc(msg.text ? msg.text.substring(0, 60) : msg.file_name || '📎') + '</div>';
    toast.addEventListener('click', function(){ openRoom(msg.room); toast.remove(); });
    EL.toastCont.appendChild(toast);
    setTimeout(function(){ if (toast.parentNode) toast.remove(); }, 4000);
  }

  /* ── Pin / Favorite ─────────────────────────────────────────────────────── */
  function togglePin() {
    if (!S.room) return;
    apiPost('/chat/api/pin', {room: S.room})
      .then(function(d){
        if (d.pinned) { if (!S.pinned.includes(S.room)) S.pinned.push(S.room); }
        else S.pinned = S.pinned.filter(function(r){ return r !== S.room; });
        renderSidebar();
        if (EL.pinBtn) EL.pinBtn.title = d.pinned ? 'בטל הצמדה' : 'הצמד';
      });
  }

  function toggleFav() {
    if (!S.room) return;
    apiPost('/chat/api/favorite', {room: S.room})
      .then(function(d){
        if (d.favorited) { if (!S.favorites.includes(S.room)) S.favorites.push(S.room); }
        else S.favorites = S.favorites.filter(function(r){ return r !== S.room; });
        renderSidebar();
      });
  }

  /* ── Scroll ─────────────────────────────────────────────────────────────── */
  function scrollBottom() {
    if (EL.messagesArea) EL.messagesArea.scrollTop = EL.messagesArea.scrollHeight;
    setTimeout(lazyLoadFiles, 300);
  }

  /* ── Input auto-resize ──────────────────────────────────────────────────── */
  function autoResizeInput() {
    if (!EL.inputField) return;
    EL.inputField.style.height = 'auto';
    EL.inputField.style.height = Math.min(EL.inputField.scrollHeight, 120) + 'px';
  }

  /* ── Event binding ──────────────────────────────────────────────────────── */
  function bindEvents() {
    // Unlock AudioContext on first user interaction (browser autoplay policy)
    document.addEventListener('click',   _unlockAudio, { once: true });
    document.addEventListener('keydown', _unlockAudio, { once: true });

    // Send button
    if (EL.sendBtn) EL.sendBtn.addEventListener('click', sendMessage);

    // Enter key (not shift)
    if (EL.inputField) {
      EL.inputField.addEventListener('keydown', function(e){
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
      });
      EL.inputField.addEventListener('input', function(){ autoResizeInput(); onTyping(); });
    }

    // Attach button
    if (EL.attachBtn) EL.attachBtn.addEventListener('click', function(){ if (EL.fileInput) EL.fileInput.click(); });
    if (EL.fileInput) EL.fileInput.addEventListener('change', function(){ if (this.files[0]) { uploadFile(this.files[0]); this.value = ''; } });

    // Drag & drop
    if (EL.main) {
      EL.main.addEventListener('dragover', function(e){ e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; });
      EL.main.addEventListener('drop', function(e){ e.preventDefault(); if (e.dataTransfer.files[0]) uploadFile(e.dataTransfer.files[0]); });
    }

    // Reply cancel
    var replyCancel = $('#chatReplyCancel');
    if (replyCancel) replyCancel.addEventListener('click', closeReplyBar);

    // Theme toggle
    if (EL.themeBtn) EL.themeBtn.addEventListener('click', function(){ applyTheme(S.theme === 'dark' ? 'light' : 'dark'); });

    // Pin / Fav
    if (EL.pinBtn) EL.pinBtn.addEventListener('click', togglePin);
    if (EL.favBtn) EL.favBtn.addEventListener('click', toggleFav);

    // Sidebar search
    if (EL.searchInput) EL.searchInput.addEventListener('input', function(){ S.searchQ = this.value; renderSidebar(); });

    // Search in conversation
    if (EL.searchInConvBtn) EL.searchInConvBtn.addEventListener('click', openSearch);
    if (EL.searchClose)     EL.searchClose.addEventListener('click', closeSearch);
    if (EL.searchPrev)      EL.searchPrev.addEventListener('click', function(){ navSearch(-1); });
    if (EL.searchNext)      EL.searchNext.addEventListener('click', function(){ navSearch(1); });
    if (EL.convSearchInput) {
      EL.convSearchInput.addEventListener('input', function(){ runSearch(); });
      EL.convSearchInput.addEventListener('keydown', function(e){
        if (e.key === 'Enter') navSearch(1);
        if (e.key === 'Escape') closeSearch();
      });
    }

    // Sound
    if (EL.soundBtn) EL.soundBtn.addEventListener('click', toggleSound);

    // Voice recording
    if (EL.voiceBtn)    EL.voiceBtn.addEventListener('click', startVoiceRecord);
    if (EL.voiceStop)   EL.voiceStop.addEventListener('click', stopVoiceRecord);
    if (EL.voiceCancel) EL.voiceCancel.addEventListener('click', cancelVoiceRecord);

    // Browser notifications
    if (EL.notifBtn) EL.notifBtn.addEventListener('click', requestNotifPermission);

    // Forward modal close
    if (EL.forwardClose)  EL.forwardClose.addEventListener('click', function(){ EL.forwardOverlay.style.display = 'none'; });
    if (EL.forwardOverlay) EL.forwardOverlay.addEventListener('click', function(e){ if (e.target === EL.forwardOverlay) EL.forwardOverlay.style.display = 'none'; });

    // Lightbox close
    if (EL.lightbox) EL.lightbox.addEventListener('click', function(){ EL.lightbox.classList.remove('show'); });

    // Close context menu on click outside
    document.addEventListener('click', function(){ if (EL.contextMenu) EL.contextMenu.classList.remove('show'); });
    document.addEventListener('click', function(){ $$('.chat-reaction-picker.show').forEach(function(p){ p.classList.remove('show'); }); });

    // Mobile back
    if (EL.mobilBack) EL.mobilBack.addEventListener('click', function(){
      if (EL.sidebar) EL.sidebar.classList.add('mobile-open');
    });

    // Sidebar toggle (for mobile) — existing app button
    var sidebarToggle = $('#sidebarToggle');
    if (sidebarToggle) {
      sidebarToggle.addEventListener('click', function(){
        if (EL.sidebar) EL.sidebar.classList.toggle('mobile-open');
      });
    }

    // Sidebar collapse / expand
    var collapseBtn = $('#chatSidebarCollapseBtn');
    var expandBtn   = $('#chatSidebarExpandBtn');
    if (collapseBtn) collapseBtn.addEventListener('click', function(){ toggleSidebarCollapse(); });
    if (expandBtn)   expandBtn.addEventListener('click',   function(){ toggleSidebarCollapse(); });

    // Sidebar resize by drag
    initSidebarResizer();
  }

  function toggleSidebarCollapse() {
    var app = $('#chatApp');
    if (!app) return;
    app.classList.toggle('sidebar-collapsed');
  }

  function initSidebarResizer() {
    var resizer = $('#chatSidebarResizer');
    var sidebar = $('#chatSidebar');
    if (!resizer || !sidebar) return;

    var dragging = false;
    var startX, startW;

    resizer.addEventListener('mousedown', function(e) {
      dragging = true;
      startX   = e.clientX;
      startW   = sidebar.getBoundingClientRect().width;
      resizer.classList.add('dragging');
      document.body.style.cursor   = 'col-resize';
      document.body.style.userSelect = 'none';
      e.preventDefault();
    });

    document.addEventListener('mousemove', function(e) {
      if (!dragging) return;
      var minW = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--chat-sidebar-min')) || 220;
      var maxW = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--chat-sidebar-max')) || 460;
      var newW = Math.min(maxW, Math.max(minW, startW + (e.clientX - startX)));
      sidebar.style.width    = newW + 'px';
      sidebar.style.minWidth = newW + 'px';
      sidebar.style.maxWidth = newW + 'px';
    });

    document.addEventListener('mouseup', function() {
      if (!dragging) return;
      dragging = false;
      resizer.classList.remove('dragging');
      document.body.style.cursor    = '';
      document.body.style.userSelect = '';
    });
  }

  /* ── Feature 1: Glassmorphism — pure CSS, no JS needed ─────────────────── */

  /* ── Feature 2: Edit message ────────────────────────────────────────────── */
  function startEditMessage(row, msg) {
    var bubble = row.querySelector('.chat-bubble-text');
    if (!bubble) return;
    var original = msg.text || '';
    var input = document.createElement('textarea');
    input.className = 'chat-edit-input';
    input.value = original;
    input.rows  = Math.min(4, (original.match(/\n/g) || []).length + 1);
    bubble.replaceWith(input);
    input.focus();
    input.select();

    function save() {
      var newText = input.value.trim();
      if (!newText || newText === original) { input.replaceWith(bubble); return; }
      apiPost('/chat/api/edit/' + msg.id, {text: newText})
        .then(function(d){
          if (!d.ok) { input.replaceWith(bubble); return; }
          var newBubble = document.createElement('div');
          newBubble.className = 'chat-bubble-text';
          newBubble.textContent = newText;
          input.replaceWith(newBubble);
          // Add edited label
          var footer = row.querySelector('.chat-bubble-footer');
          if (footer && !footer.querySelector('.chat-edited-label')) {
            var label = document.createElement('span');
            label.className = 'chat-edited-label';
            label.textContent = 'ערוך';
            footer.insertBefore(label, footer.firstChild);
          }
        });
    }

    input.addEventListener('keydown', function(e){
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); save(); }
      if (e.key === 'Escape') { input.replaceWith(bubble); }
    });
    input.addEventListener('blur', save);
  }

  /* ── Feature 3: Forward message ─────────────────────────────────────────── */
  function openForwardModal(msg) {
    S.forwardMsgId = msg.id;
    if (!EL.forwardList || !EL.forwardOverlay) return;

    var html = '';
    S.conversations.forEach(function(c){
      if (c.room === S.room) return; // skip current room
      var avatar = c.type === 'dm'
        ? roleAvatar(c.role, 'sm')
        : '<div class="role-avatar-sm role-admin"><i class="bi ' + (c.icon||'bi-chat') + '"></i></div>';
      html += '<div class="chat-modal-item" data-room="' + _esc(c.room) + '" data-rcv="' + _esc(c.user_id||'') + '">' +
        avatar + '<span class="item-name">' + _esc(c.name) + '</span></div>';
    });
    EL.forwardList.innerHTML = html || '<div class="p-4 text-center text-muted" style="font-size:.85rem;">אין שיחות אחרות</div>';

    EL.forwardList.querySelectorAll('.chat-modal-item').forEach(function(el){
      el.addEventListener('click', function(){
        executeForward(S.forwardMsgId, el.dataset.room, el.dataset.rcv || null);
        EL.forwardOverlay.style.display = 'none';
      });
    });

    EL.forwardOverlay.style.display = 'flex';
  }

  function executeForward(msgId, targetRoom, receiverId) {
    apiPost('/chat/api/forward', {msg_id: msgId, target_room: targetRoom, receiver_id: receiverId || null})
      .then(function(d){
        if (d.ok) {
          showToast({user_name: S.meName, text: '→ הועבר', room: targetRoom});
        }
      });
  }

  /* ── Feature 4: Search inside conversation ──────────────────────────────── */
  function openSearch() {
    if (!EL.searchInConv) return;
    EL.searchInConv.classList.add('show');
    EL.searchInConv.style.display = '';
    if (EL.convSearchInput) EL.convSearchInput.focus();
  }

  function closeSearch() {
    if (!EL.searchInConv) return;
    EL.searchInConv.classList.remove('show');
    EL.searchInConv.style.display = 'none';
    clearSearchHighlights();
    S.searchResults = [];
    S.searchIdx     = -1;
    if (EL.searchCount) EL.searchCount.textContent = '';
    if (EL.convSearchInput) EL.convSearchInput.value = '';
  }

  function runSearch() {
    var q = EL.convSearchInput ? EL.convSearchInput.value.trim() : '';
    clearSearchHighlights();
    if (!q || q.length < 2 || !S.room) {
      if (EL.searchCount) EL.searchCount.textContent = '';
      S.searchResults = []; S.searchIdx = -1;
      return;
    }

    fetch('/chat/api/search?room=' + encodeURIComponent(S.room) + '&q=' + encodeURIComponent(q))
      .then(function(r){ return r.json(); })
      .then(function(d){
        S.searchResults = d.results || [];
        S.searchIdx     = S.searchResults.length ? 0 : -1;
        highlightResults(q);
        updateSearchCount();
        scrollToResult(S.searchIdx);
      });
  }

  function highlightResults(q) {
    if (!EL.messagesArea) return;
    var re = new RegExp('(' + q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi');
    S.searchResults.forEach(function(r){
      var row = EL.messagesArea.querySelector('[data-id="' + r.id + '"]');
      if (!row) return;
      row.classList.add('chat-msg-highlight');
      var textEl = row.querySelector('.chat-bubble-text');
      if (textEl) textEl.innerHTML = textEl.textContent.replace(re, '<mark class="chat-mark">$1</mark>');
    });
  }

  function clearSearchHighlights() {
    if (!EL.messagesArea) return;
    $$('.chat-msg-highlight', EL.messagesArea).forEach(function(row){
      row.classList.remove('chat-msg-highlight');
      var textEl = row.querySelector('.chat-bubble-text');
      if (textEl) textEl.innerHTML = textEl.textContent; // strip marks
    });
  }

  function updateSearchCount() {
    if (!EL.searchCount) return;
    if (!S.searchResults.length) { EL.searchCount.textContent = '0 תוצאות'; return; }
    EL.searchCount.textContent = (S.searchIdx + 1) + ' / ' + S.searchResults.length;
  }

  function scrollToResult(idx) {
    if (idx < 0 || idx >= S.searchResults.length || !EL.messagesArea) return;
    var id  = S.searchResults[idx].id;
    var row = EL.messagesArea.querySelector('[data-id="' + id + '"]');
    if (row) row.scrollIntoView({behavior:'smooth', block:'center'});
    updateSearchCount();
  }

  function navSearch(dir) {
    if (!S.searchResults.length) return;
    S.searchIdx = (S.searchIdx + dir + S.searchResults.length) % S.searchResults.length;
    scrollToResult(S.searchIdx);
  }

  /* ── Feature 5: Sound notifications ────────────────────────────────────── */

  // Single shared AudioContext — browsers block new contexts without a user gesture.
  // We create it lazily on the first user interaction and reuse it forever.
  var _audioCtx = null;

  function _getAudioCtx() {
    if (!_audioCtx) {
      try { _audioCtx = new (window.AudioContext || window.webkitAudioContext)(); } catch(e) {}
    }
    return _audioCtx;
  }

  // Call once on any user gesture to unlock the context (browser policy)
  function _unlockAudio() {
    var ctx = _getAudioCtx();
    if (ctx && ctx.state === 'suspended') ctx.resume();
  }

  function _doPlayPing(ctx) {
    var osc  = ctx.createOscillator();
    var gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.type = 'sine';
    osc.frequency.setValueAtTime(880, ctx.currentTime);
    osc.frequency.setValueAtTime(660, ctx.currentTime + 0.1);
    gain.gain.setValueAtTime(0.3, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.35);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + 0.35);
  }

  function playPing() {
    if (S.soundMuted) return;
    try {
      var ctx = _getAudioCtx();
      if (!ctx) return;
      if (ctx.state === 'suspended') {
        ctx.resume().then(function() { _doPlayPing(ctx); });
      } else {
        _doPlayPing(ctx);
      }
    } catch(e) {}
  }

  function toggleSound() {
    _unlockAudio();   // first toggle also unlocks the context
    S.soundMuted = !S.soundMuted;
    localStorage.setItem('chat-sound-muted', S.soundMuted ? '1' : '0');
    updateSoundBtn();
  }

  function updateSoundBtn() {
    if (!EL.soundBtn) return;
    EL.soundBtn.innerHTML = S.soundMuted
      ? '<i class="bi bi-volume-mute"></i>'
      : '<i class="bi bi-volume-up"></i>';
    EL.soundBtn.title = S.soundMuted ? 'הפעל צליל' : 'השתק';
  }

  /* ── Feature 6: Browser notifications ──────────────────────────────────── */
  function requestNotifPermission() {
    if (!('Notification' in window)) return;
    Notification.requestPermission().then(updateNotifBtn);
  }

  function showBrowserNotification(msg) {
    if (!('Notification' in window) || Notification.permission !== 'granted') return;
    if (!document.hidden) return;
    if (msg.room === S.room) return;
    try {
      var n = new Notification(msg.user_name || 'Chat', {
        body: msg.text ? msg.text.substring(0, 80) : '📎 ' + (msg.file_name || 'קובץ'),
        tag:  msg.room,
      });
      n.onclick = function(){
        window.focus();
        openRoom(msg.room);
        n.close();
      };
      setTimeout(function(){ n.close(); }, 6000);
    } catch(e) {}
  }

  function updateNotifBtn() {
    if (!EL.notifBtn) return;
    if (!('Notification' in window)) { EL.notifBtn.style.display = 'none'; return; }
    var perm = Notification.permission;
    EL.notifBtn.innerHTML = perm === 'granted'
      ? '<i class="bi bi-bell-fill text-primary"></i>'
      : perm === 'denied'
      ? '<i class="bi bi-bell-slash"></i>'
      : '<i class="bi bi-bell"></i>';
    EL.notifBtn.title = perm === 'granted' ? 'התראות פעילות' : 'הפעל התראות';
  }

  /* ── Helpers ────────────────────────────────────────────────────────────── */
  function roleAvatar(role, size) {
    var cls = 'role-viewer', icon = 'bi-eye-fill';
    if (role === 'super_admin') { cls = 'role-super'; icon = 'bi-shield-fill-check'; }
    else if (role === 'admin')  { cls = 'role-admin'; icon = 'bi-crown-fill'; }
    else if (role === 'warehouse') { cls = 'role-tech'; icon = 'bi-box-seam-fill'; }
    var sz = size ? 'role-avatar-' + size : 'role-avatar';
    return '<div class="' + sz + ' ' + cls + '"><i class="bi ' + icon + '"></i></div>';
  }

  function _esc(s) {
    return String(s||'')
      .replace(/&/g,'&amp;').replace(/</g,'&lt;')
      .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  function apiPost(url, data) {
    return fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': S.csrf },
      body: JSON.stringify(data),
    }).then(function(r){ return r.json(); });
  }

  /* ── Voice recording ────────────────────────────────────────────────────── */
  var _vRecorder   = null;
  var _vChunks     = [];
  var _vTimerInt   = null;
  var _vSecs       = 0;
  var _vStream     = null;
  var _vRecording  = false;

  function _doGetMic() {
    navigator.mediaDevices.getUserMedia({ audio: true })
      .then(function(stream) {
        _vStream    = stream;
        _vChunks    = [];
        _vSecs      = 0;
        _vRecording = true;

        if (EL.voiceBtn)   EL.voiceBtn.classList.add('recording');
        if (EL.voiceBar)   EL.voiceBar.classList.add('show');
        if (EL.voiceTimer) EL.voiceTimer.textContent = '00:00';

        _vTimerInt = setInterval(function() {
          _vSecs++;
          var m = String(Math.floor(_vSecs / 60)).padStart(2, '0');
          var s = String(_vSecs % 60).padStart(2, '0');
          if (EL.voiceTimer) EL.voiceTimer.textContent = m + ':' + s;
          if (_vSecs >= 120) stopVoiceRecord();
        }, 1000);

        var mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/ogg']
          .find(function(t) { return MediaRecorder.isTypeSupported(t); }) || '';

        _vRecorder = new MediaRecorder(stream, mime ? { mimeType: mime } : {});
        _vRecorder.ondataavailable = function(e) {
          if (e.data && e.data.size > 0) _vChunks.push(e.data);
        };
        _vRecorder.onstop = function() {
          _vStream.getTracks().forEach(function(t) { t.stop(); });
          var mimeUsed = _vRecorder.mimeType || 'audio/webm';
          _sendVoiceBlob(new Blob(_vChunks, { type: mimeUsed }), mimeUsed);
        };
        _vRecorder.start(200);
      })
      .catch(function(err) {
        _showMicError(err);
      });
  }

  function _showMicError(err) {
    // Remove any leftover permission dialog
    var old = document.getElementById('chatMicDialog');
    if (old) old.remove();

    var msg, action = '';
    if (err && (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError')) {
      msg    = 'ההרשאה לגישה למיקרופון נחסמה.';
      action = 'לחץ על אייקון 🔒 / 🎤 בשורת הכתובת → מיקרופון → אפשר → רענן את הדף.';
    } else if (err && err.name === 'NotFoundError') {
      msg = 'לא נמצא מיקרופון במכשיר.';
    } else {
      msg = 'שגיאה בגישה למיקרופון' + (err ? ': ' + err.name : '') + '.';
    }

    var dlg = document.createElement('div');
    dlg.id = 'chatMicDialog';
    dlg.style.cssText = 'position:fixed;inset:0;z-index:99999;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.45)';
    dlg.innerHTML = '<div style="background:#fff;border-radius:14px;padding:28px 32px;max-width:340px;text-align:center;box-shadow:0 8px 40px rgba(0,0,0,.25)">' +
      '<div style="font-size:2.2rem;margin-bottom:10px;">🎤</div>' +
      '<div style="font-weight:700;font-size:1rem;margin-bottom:8px;">' + msg + '</div>' +
      (action ? '<div style="font-size:.85rem;color:#6b7280;margin-bottom:18px;">' + action + '</div>' : '<div style="height:10px"></div>') +
      '<button id="chatMicDialogClose" style="background:#2563eb;color:#fff;border:none;border-radius:8px;padding:9px 28px;font-size:.9rem;font-weight:600;cursor:pointer;">הבנתי</button>' +
      '</div>';
    document.body.appendChild(dlg);
    dlg.querySelector('#chatMicDialogClose').addEventListener('click', function() { dlg.remove(); });
    dlg.addEventListener('click', function(e) { if (e.target === dlg) dlg.remove(); });
  }

  function startVoiceRecord() {
    if (_vRecording) return;
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      _showMicError({ name: 'NotSupportedError' });
      return;
    }

    // Check existing permission state without prompting yet
    if (navigator.permissions && navigator.permissions.query) {
      navigator.permissions.query({ name: 'microphone' }).then(function(perm) {
        if (perm.state === 'denied') {
          _showMicError({ name: 'NotAllowedError' });
        } else {
          // 'granted' or 'prompt' — show our dialog first if never asked before
          if (perm.state === 'prompt') {
            _showMicPermissionDialog(_doGetMic);
          } else {
            _doGetMic();
          }
        }
      }).catch(function() {
        // Permissions API not available — go straight to getUserMedia
        _doGetMic();
      });
    } else {
      _doGetMic();
    }
  }

  function _showMicPermissionDialog(onConfirm) {
    var old = document.getElementById('chatMicDialog');
    if (old) old.remove();

    var dlg = document.createElement('div');
    dlg.id = 'chatMicDialog';
    dlg.style.cssText = 'position:fixed;inset:0;z-index:99999;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.45)';
    dlg.innerHTML = '<div style="background:#fff;border-radius:14px;padding:28px 32px;max-width:340px;text-align:center;box-shadow:0 8px 40px rgba(0,0,0,.25)">' +
      '<div style="font-size:2.2rem;margin-bottom:10px;">🎤</div>' +
      '<div style="font-weight:700;font-size:1rem;margin-bottom:8px;">האם לאפשר הקלטת הודעות?</div>' +
      '<div style="font-size:.85rem;color:#6b7280;margin-bottom:20px;">הדפדפן יבקש גישה למיקרופון שלך כדי לשלוח הודעות קוליות.</div>' +
      '<div style="display:flex;gap:10px;justify-content:center;">' +
        '<button id="chatMicYes" style="background:#2563eb;color:#fff;border:none;border-radius:8px;padding:9px 24px;font-size:.9rem;font-weight:600;cursor:pointer;">אפשר הקלטה</button>' +
        '<button id="chatMicNo"  style="background:#f3f4f6;color:#374151;border:none;border-radius:8px;padding:9px 24px;font-size:.9rem;cursor:pointer;">ביטול</button>' +
      '</div>' +
      '</div>';
    document.body.appendChild(dlg);
    dlg.querySelector('#chatMicYes').addEventListener('click', function() {
      dlg.remove();
      onConfirm();
    });
    dlg.querySelector('#chatMicNo').addEventListener('click', function() { dlg.remove(); });
    dlg.addEventListener('click', function(e) { if (e.target === dlg) dlg.remove(); });
  }

  function stopVoiceRecord() {
    if (!_vRecording) return;
    _vRecording = false;
    clearInterval(_vTimerInt);
    if (EL.voiceBtn)  EL.voiceBtn.classList.remove('recording');
    if (EL.voiceBar)  EL.voiceBar.classList.remove('show');
    if (_vRecorder && _vRecorder.state !== 'inactive') _vRecorder.stop();
  }

  function cancelVoiceRecord() {
    if (!_vRecording) return;
    _vRecording = false;
    clearInterval(_vTimerInt);
    if (EL.voiceBtn) EL.voiceBtn.classList.remove('recording');
    if (EL.voiceBar) EL.voiceBar.classList.remove('show');
    // Stop recorder without sending
    if (_vRecorder && _vRecorder.state !== 'inactive') {
      _vRecorder.ondataavailable = null;
      _vRecorder.onstop = function() {};
      _vRecorder.stop();
    }
    if (_vStream) _vStream.getTracks().forEach(function(t) { t.stop(); });
  }

  function _sendVoiceBlob(blob, mimeType) {
    if (!S.room) return;
    if (_vSecs < 1) return; // ignore < 1s recordings
    var ext  = mimeType.includes('ogg') ? '.ogg' : '.webm';
    var name = 'voice_' + Date.now() + ext;
    var file = new File([blob], name, { type: mimeType });
    var fd   = new FormData();
    fd.append('file', file);
    fd.append('room', S.room);
    if (S.receiverId) fd.append('receiver_id', S.receiverId);

    fetch('/chat/api/upload', {
      method: 'POST',
      headers: { 'X-CSRFToken': S.csrf },
      body: fd,
    })
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (d.ok && d.message) {
        if (!EL.messagesArea.querySelector('[data-id="' + d.message.id + '"]')) {
          appendMessage(d.message, true);
          if (S.lastTs === null || d.message._iso > S.lastTs) S.lastTs = d.message._iso;
          scrollBottom();
        }
      }
    })
    .catch(function() { alert('שגיאה בשליחת ההקלטה. נסה שוב.'); });
  }

  /* ── Boot ───────────────────────────────────────────────────────────────── */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
