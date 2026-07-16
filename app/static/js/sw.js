const CACHE = 'netstock-v8';
const PRECACHE = [
  '/static/loading.html',
  '/static/css/style.css',
  '/static/js/app.js',
  '/static/img/logo.png',
  '/static/video/poster.jpg',
  '/static/video/intro.mp4',
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

  // Navigation to '/' — try the real server first (warm = fast).
  // Only fall back to loading.html if the server doesn't respond within 2s (cold start / Render sleep).
  if (e.request.mode === 'navigate' && url.pathname === '/' && !url.searchParams.has('ready')) {
    e.respondWith(
      Promise.race([
        fetch(e.request.clone(), { credentials: 'include' }),
        new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), 2000))
      ]).catch(() =>
        caches.match('/static/loading.html')
          .then(cached => cached || fetch(e.request, { credentials: 'include' }))
      )
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
