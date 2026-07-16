const CACHE = 'netstock-v5';
const PRECACHE = [
  '/static/loading.html',
  '/static/css/style.css',
  '/static/js/app.js',
  '/static/img/logo.png',
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

  // Navigation to '/' — immediately show loading screen from cache
  // loading.html polls /api/ping and redirects to /?ready=1 when server is up
  if (e.request.mode === 'navigate' && url.pathname === '/' && !url.searchParams.has('ready')) {
    e.respondWith(
      caches.match('/static/loading.html').then(cached => {
        if (cached) return cached;
        // Fallback: pass through if cache miss (first load before SW installs)
        return fetch(e.request, { credentials: 'include' });
      })
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
