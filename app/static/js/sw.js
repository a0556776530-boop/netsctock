const CACHE = 'netstock-v14';
const PRECACHE = [
  '/static/loading.html',
  '/static/css/style.css',
  '/static/js/app.js',
  '/static/img/logo.png',
  '/static/video/poster.jpg',
  // intro.mp4 (14MB) is NOT precached — too large for install; cached on first play instead
];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(PRECACHE)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  const url = new URL(e.request.url);

  // Navigation to '/'
  if (e.request.mode === 'navigate' && url.pathname === '/') {
    const referrer   = e.request.referrer || '';
    const fromInside = referrer && referrer.startsWith(self.location.origin);

    if (fromInside) {
      // Coming from within the app — pass straight through, no splash
      return;
    }

    // Fresh open (PWA icon / browser / bookmark) — always show the intro
    e.respondWith(
      caches.match('/static/loading.html')
        .then(c => c || fetch(e.request, { credentials: 'include' }))
    );
    return;
  }

  // Static assets — cache first
  if (url.pathname.startsWith('/static/')) {
    e.respondWith(
      caches.match(e.request).then(cached => cached || fetch(e.request).then(res => {
        const clone = res.clone();
        caches.open(CACHE).then(c => c.put(e.request, clone));
        return res;
      }))
    );
  }
});
