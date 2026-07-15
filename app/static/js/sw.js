const CACHE = 'netstock-v2';
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

  // Navigation to '/' — race server vs 1.5s timeout
  if (e.request.mode === 'navigate' && url.pathname === '/') {
    e.respondWith(
      Promise.race([
        fetch(e.request, { credentials: 'include' }),
        new Promise(resolve => setTimeout(() => resolve(null), 1500)),
      ]).then(result => {
        if (result) return result;
        // Server too slow — serve loading page from cache
        return caches.match('/static/loading.html');
      }).catch(() => caches.match('/static/loading.html'))
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
