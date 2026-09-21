{% comment %}The alerts service worker, served from the site root.

   **From `/`, not `/static/`, and that is not a preference.** A worker's scope
   is the directory it is served from, so one at `/static/alerts/sw.js` could
   only ever receive events for `/static/alerts/`. The site already serves
   `robots.txt` from root through `core_views.index_file`; this follows it.

   A template rather than a static file because it is served by a view, and
   because the copy below belongs with the site's other copy.
{% endcomment %}
// Delivered when a push arrives, whether or not a tab is open. `event.data` is
// what `push.py` sent; the browser shows nothing unless this asks it to.
self.addEventListener("push", function (event) {
  var payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch (error) {
    // A malformed payload must still notify: silence would be indistinguishable
    // from the alert never having fired, which is the failure a reader cannot
    // diagnose and we cannot see.
    payload = {};
  }

  event.waitUntil(
    self.registration.showNotification(payload.title || "{{ WEBSITE_NAME }}", {
      body: payload.body || "",
      // A tag replaces an earlier notification with the same one rather than
      // stacking, so a rule that fires twice while the phone is locked leaves
      // one line rather than two.
      tag: payload.tag || "asastats-alert",
      data: { url: payload.url || "/" },
    })
  );
});

// Focus an open tab rather than opening a second one: a reader who already has
// the page does not want another copy of it.
self.addEventListener("notificationclick", function (event) {
  event.notification.close();
  var target = (event.notification.data && event.notification.data.url) || "/";
  event.waitUntil(
    self.clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then(function (windows) {
        for (var i = 0; i < windows.length; i += 1) {
          if (windows[i].url.indexOf(target) !== -1 && "focus" in windows[i]) {
            return windows[i].focus();
          }
        }
        return self.clients.openWindow(target);
      })
  );
});
