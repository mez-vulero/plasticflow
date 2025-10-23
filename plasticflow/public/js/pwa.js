(() => {
	if (typeof window === "undefined") {
		return;
	}

	// Register service worker for Desk
	const registerServiceWorker = () => {
		if ("serviceWorker" in navigator) {
			navigator.serviceWorker
				.register("/assets/plasticflow/service-worker.js")
				.catch((error) => {
					console.error("[PlasticFlow] Service worker registration failed:", error);
				});
		}
	};

	const ensureManifestLink = () => {
		const manifestHref = "/assets/plasticflow/manifest.json";
		let link = document.querySelector("link[rel='manifest']");
		if (!link) {
			link = document.createElement("link");
			link.rel = "manifest";
			document.head.appendChild(link);
		}
		link.href = manifestHref;
	};

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", () => {
			ensureManifestLink();
			registerServiceWorker();
		});
	} else {
		ensureManifestLink();
		registerServiceWorker();
	}
})();
