// Minimal service worker. Android Chrome can only show notifications
// through a service worker (it has no `new Notification()`). It does
// not cache anything, so it never serves stale pages.

self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

// Tapping a wandering alert brings the app back to the front.
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(
    self.clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then((clients) => (clients[0] ? clients[0].focus() : self.clients.openWindow("/")))
  );
});
