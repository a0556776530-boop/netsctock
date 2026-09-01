// Service worker — install/activate only (push notifications removed)

self.addEventListener('install', function (e) {
  self.skipWaiting();
});

self.addEventListener('activate', function (e) {
  e.waitUntil(clients.claim());
});
