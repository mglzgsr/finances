// Service Worker básico — solo para hacer la app instalable
const CACHE = 'finances-v1';

self.addEventListener('install', e => {
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(clients.claim());
});

// Sin caché agresivo — siempre red primero para datos financieros
self.addEventListener('fetch', e => {
  // Solo cachear assets estáticos
  if (e.request.url.includes('/static/') || e.request.url.includes('fonts.googleapis')) {
    e.respondWith(
      caches.open(CACHE).then(cache =>
        cache.match(e.request).then(cached =>
          cached || fetch(e.request).then(res => {
            cache.put(e.request, res.clone());
            return res;
          })
        )
      )
    );
  }
  // Todo lo demás (API, HTML) siempre desde red
});
