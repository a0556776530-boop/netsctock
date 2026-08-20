// ── Cache config ─────────────────────────────────────────────────────────────
var CACHE = 'netstock-v3';
var STATIC_ASSETS = [
  '/static/css/style.css',
  '/static/css/chat.css',
  '/static/js/app.js',
  '/static/js/chat.js',
  '/static/img/logo.png',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.rtl.min.css',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js',
  'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css',
  'https://cdn.socket.io/4.6.1/socket.io.min.js',
];

// ── Install: pre-cache all static assets ─────────────────────────────────────
self.addEventListener('install', function (e) {
  e.waitUntil(
    caches.open(CACHE).then(function (cache) {
      return Promise.allSettled(
        STATIC_ASSETS.map(function (url) {
          return cache.add(url).catch(function () { /* skip if unavailable */ });
        })
      );
    }).then(function () { return self.skipWaiting(); })
  );
});

// ── Activate: delete old caches ───────────────────────────────────────────────
self.addEventListener('activate', function (e) {
  e.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(
        keys.filter(function (k) { return k !== CACHE; })
            .map(function (k) { return caches.delete(k); })
      );
    }).then(function () { return self.clients.claim(); })
  );
});

// ── Fetch: Cache-first for static assets, network-first for everything else ───
self.addEventListener('fetch', function (e) {
  var req = e.request;
  var url = req.url;

  // Only handle GET requests
  if (req.method !== 'GET') return;

  // Never intercept HTML page navigation — browser handles it directly
  if (e.request.mode === 'navigate') return;

  // Skip API, Socket.IO polling, and auth endpoints — always network
  if (url.includes('/api/') || url.includes('/socket.io') || url.includes('/auth/')) return;

  var isStatic = url.includes('/static/') ||
                 url.includes('cdn.jsdelivr.net') ||
                 url.includes('fonts.googleapis.com') ||
                 url.includes('fonts.gstatic.com') ||
                 url.includes('cdn.socket.io');

  if (isStatic) {
    // Cache-first: serve from cache instantly, refresh in background
    e.respondWith(
      caches.open(CACHE).then(function (cache) {
        return cache.match(req).then(function (cached) {
          var fetchPromise = fetch(req).then(function (res) {
            if (res && res.status === 200) cache.put(req, res.clone());
            return res;
          }).catch(function () { return cached; });
          return cached || fetchPromise;
        });
      })
    );
  }
  // HTML navigation: network-first (always fresh from server)
  // — no interception, let browser handle normally
});

// ── Push notifications ────────────────────────────────────────────────────────
self.addEventListener('push', function (e) {
  var data = {};
  try { data = e.data.json(); } catch (_) {}
  var title = data.title || 'NetStock Chat';
  var opts  = {
    body:  data.body  || 'הודעה חדשה',
    icon:  data.icon  || '/static/img/logo.png',
    badge: data.icon  || '/static/img/logo.png',
    tag:   data.room  || 'chat',
    renotify: true,
    data:  { url: data.url || '/chat' },
    dir:   'rtl',
    lang:  'he',
  };
  e.waitUntil(self.registration.showNotification(title, opts));
});

self.addEventListener('notificationclick', function (e) {
  e.notification.close();
  var target = (e.notification.data && e.notification.data.url) || '/chat';
  e.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (list) {
      for (var i = 0; i < list.length; i++) {
        var c = list[i];
        if (c.url.indexOf('/chat') !== -1 && 'focus' in c) return c.focus();
      }
      if (clients.openWindow) return clients.openWindow(target);
    })
  );
});
