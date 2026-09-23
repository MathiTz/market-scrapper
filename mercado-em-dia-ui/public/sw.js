const CACHE = "mercado-shell-v1";
self.addEventListener("install", (e) =>
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(["/offline.html", "/icon.svg"])),
  ),
);
self.addEventListener("activate", (e) =>
  e.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)),
        ),
      ),
  ),
);
self.addEventListener("fetch", (e) => {
  if (
    e.request.method !== "GET" ||
    new URL(e.request.url).pathname.startsWith("/api/")
  )
    return;
  if (e.request.mode === "navigate")
    e.respondWith(fetch(e.request).catch(() => caches.match("/offline.html")));
});
