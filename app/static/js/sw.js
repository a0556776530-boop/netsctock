const CACHE    = 'netstock-v11';
const WARM_KEY = '__warm__';
const WARM_TTL = 10 * 60 * 1000; // 10 minutes

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

// Pages send this message when they successfully load → server is up
self.addEventListener('message', e => {
  if (e.data && e.data.type === 'SERVER_WARM') markWarm();
});

async function isWarm() {
  try {
    const c = await caches.open(CACHE);
    const r = await c.match(WARM_KEY);
    if (!r) return false;
    return (Date.now() - parseInt(await r.text(), 10)) < WARM_TTL;
  } catch { return false; }
}

async function markWarm() {
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

  // /?ready=1 — loading.html confirmed server alive
  if (e.request.mode === 'navigate' && url.pathname === '/' && url.searchParams.has('ready')) {
    markWarm();
    return;
  }

  // Navigation to '/'
  if (e.request.mode === 'navigate' && url.pathname === '/') {
    e.respondWith(
      isWarm().then(warm => {
        if (warm) {
          // Server was recently confirmed alive — pass straight through
          return fetch(e.request, { credentials: 'include' });
        }
        // Cold start: race server vs 3s timeout
        return Promise.race([
          fetch(e.request.clone(), { credentials: 'include' })
            .then(resp => { markWarm(); return resp; }),
          new Promise((_, reject) => setTimeout(() => reject(), 3000))
        ]).catch(() =>
          caches.match('/static/loading.html')
            .then(c => c || fetch(e.request, { credentials: 'include' }))
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
