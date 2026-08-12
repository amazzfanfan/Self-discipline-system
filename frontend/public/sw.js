self.addEventListener('push', (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { title: 'System Agent', body: event.data ? event.data.text() : '' };
  }
  event.waitUntil(self.registration.showNotification(data.title || 'System Agent', {
    body: data.body || '你有一条新提醒',
    tag: data.notification_id || data.kind || 'system-agent',
    data: { link: data.link || '/' },
    icon: '/favicon.svg',
    badge: '/favicon.svg',
  }));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const target = new URL(event.notification.data?.link || '/', self.location.origin).href;
  event.waitUntil((async () => {
    const windows = await clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const windowClient of windows) {
      if ('navigate' in windowClient) await windowClient.navigate(target);
      return windowClient.focus();
    }
    return clients.openWindow(target);
  })());
});
