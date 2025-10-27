const CACHE_NAME = "plasticflow-cache-v2";
const OFFLINE_URLS = ["/app"];

self.addEventListener("install", (event) => {
	event.waitUntil(
		caches.open(CACHE_NAME).then((cache) => {
			return cache.addAll(OFFLINE_URLS);
		})
	);
	self.skipWaiting();
});

self.addEventListener("activate", (event) => {
	event.waitUntil(
		caches.keys().then((cacheNames) =>
			Promise.all(
				cacheNames
					.filter((cacheName) => cacheName !== CACHE_NAME)
					.map((cacheName) => caches.delete(cacheName))
			)
		)
	);
	self.clients.claim();
});

self.addEventListener("fetch", (event) => {
	if (event.request.method !== "GET") {
		return;
	}

	event.respondWith(
		caches.match(event.request).then((cachedResponse) => {
			if (cachedResponse) {
				return cachedResponse;
			}

			return fetch(event.request)
				.then((response) => {
					const responseClone = response.clone();
					caches.open(CACHE_NAME).then((cache) => {
						cache.put(event.request, responseClone);
					});
					return response;
				})
				.catch(() => caches.match("/app"));
		})
	);
});
