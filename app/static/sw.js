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
        if (c.url.indexOf('/chat') !== -1 && 'focus' in c) {
          return c.focus();
        }
      }
      if (clients.openWindow) return clients.openWindow(target);
    })
  );
});
