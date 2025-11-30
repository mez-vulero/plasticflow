const CACHE_NAME = "plasticflow-cache-v3";
const OFFLINE_URLS = ["/app"];
const DEFAULT_NOTIFICATION_TITLE = "PlasticFlow";

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

self.addEventListener("push", (event) => {
	let payload = {};
	try {
		payload = event.data ? event.data.json() : {};
	} catch (error) {
		payload = {
			body: event.data ? event.data.text() : "",
		};
	}

	const title = payload.title || DEFAULT_NOTIFICATION_TITLE;
	const options = {
		body: payload.body || "",
		data: {
			reference_doctype: payload.reference_doctype || null,
			reference_name: payload.reference_name || null,
		},
		icon: "/assets/plasticflow/pwa-icon-192.png",
		badge: "/assets/plasticflow/pwa-icon-192.png",
		vibrate: [100, 50, 100],
	};

	event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
	event.notification.close();

	const { reference_doctype, reference_name } = event.notification.data || {};

	// Focus existing client or open a new window
	event.waitUntil(
		self.clients
			.matchAll({ type: "window", includeUncontrolled: true })
			.then((clientList) => {
				for (const client of clientList) {
					if ("focus" in client) {
						client.postMessage({
							type: "plasticflow.push.open",
							reference_doctype,
							reference_name,
						});
						return client.focus();
					}
				}

				let targetUrl = "/app";
				if (reference_doctype && reference_name) {
					targetUrl = `/app/${reference_doctype.toLowerCase().replace(/ /g, "-")}/${reference_name}`;
				}

				if (self.clients.openWindow) {
					return self.clients.openWindow(targetUrl);
				}
			})
	);
});
