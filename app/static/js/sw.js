const CACHE = 'netstock-v9';
const PRECACHE = [
  '/static/loading.html',
  '/static/css/style.css',
  '/static/js/app.js',
  '/static/img/logo.png',
  '/static/video/poster.jpg',
  '/static/video/intro.mp4',
];

// Key used to store the "server is warm" timestamp inside the cache
const WARM_KEY = '__server_warm__';
// How long a warm confirmation stays valid (10 minutes)
const WARM_TTL = 10 * 60 * 1000;

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

async function isServerWarm() {
  try {
    const c = await caches.open(CACHE);
    const r = await c.match(WARM_KEY);
    if (!r) return false;
    const ts = parseInt(await r.text(), 10);
    return (Date.now() - ts) < WARM_TTL;
  } catch { return false; }
}

async function markServerWarm() {
  try {
    const c = await caches.open(CACHE);
    await c.put(WARM_KEY, new Response(String(Date.now()), {
      headers: { 'Content-Type': 'text/plain' }
    }));
  } catch {}
}

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  const url = new URL(e.request.url);

  // /?ready=1 — loading.html confirmed server is up; mark warm and let through
  if (e.request.mode === 'navigate' && url.pathname === '/' && url.searchParams.has('ready')) {
    markServerWarm();
    return; // browser handles normally
  }

  // Navigation to '/' (dashboard)
  if (e.request.mode === 'navigate' && url.pathname === '/') {
    e.respondWith(
      isServerWarm().then(warm => {
        if (warm) {
          // Server was recently confirmed alive — go straight to dashboard
          return fetch(e.request, { credentials: 'include' });
        }
        // Unknown state (first open / long idle) — race: server vs 2s timeout
        return Promise.race([
          fetch(e.request.clone(), { credentials: 'include' })
            .then(resp => { markServerWarm(); return resp; }),
          new Promise((_, reject) => setTimeout(() => reject(new Error('cold')), 2000))
        ]).catch(() =>
          // Server didn't respond in time — show loading splash
          caches.match('/static/loading.html')
            .then(cached => cached || fetch(e.request, { credentials: 'include' }))
        );
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
