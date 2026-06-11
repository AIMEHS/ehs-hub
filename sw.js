/* EHS Hub service worker — offline app shell (ticket #11).
   Caches only same-origin static assets. Supabase + eCFR calls always go to
   the network so regulatory text is never served stale. */
var CACHE = "hub-shell-v1";
self.addEventListener("install", function (e) {
  e.waitUntil(
    caches.open(CACHE).then(function (c) { return c.addAll(["/"]); }).then(function () { return self.skipWaiting(); })
  );
});
self.addEventListener("activate", function (e) {
  e.waitUntil(
    caches.keys().then(function (ks) {
      return Promise.all(ks.filter(function (k) { return k !== CACHE; }).map(function (k) { return caches.delete(k); }));
    }).then(function () { return self.clients.claim(); })
  );
});
self.addEventListener("fetch", function (e) {
  var u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.origin !== location.origin) return;
  var isShell = (u.pathname === "/" || u.pathname === "/index.html");
  var isStatic = /\.(json|svg|png|txt|xml)$/.test(u.pathname);
  if (isShell) {
    // network-first: deploys land normally; offline falls back to the cached shell
    e.respondWith(
      fetch(e.request).then(function (r) {
        var cp = r.clone(); caches.open(CACHE).then(function (c) { c.put("/", cp); }); return r;
      }).catch(function () { return caches.match("/"); })
    );
  } else if (isStatic) {
    // stale-while-revalidate for struct JSONs, logos, robots/sitemap
    e.respondWith(
      caches.match(e.request).then(function (hit) {
        var net = fetch(e.request).then(function (r) {
          var cp = r.clone(); caches.open(CACHE).then(function (c) { c.put(e.request, cp); }); return r;
        }).catch(function () { return hit; });
        return hit || net;
      })
    );
  }
});
