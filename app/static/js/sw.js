const CACHE = 'netstock-v12';
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

  // Navigation to '/' — try server first (3s). If no response → cold start → show loading screen.
  if (e.request.mode === 'navigate' && url.pathname === '/') {
    e.respondWith(
      Promise.race([
        fetch(e.request.clone(), { credentials: 'include' }),
        new Promise((_, reject) => setTimeout(reject, 3000))
      ]).catch(() =>
        caches.match('/static/loading.html')
          .then(c => c || fetch(e.request, { credentials: 'include' }))
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
