(() => {
	if (typeof window === "undefined") {
		return;
	}

	const PUSH_STORAGE_KEY = "plasticflow.push.last_prompt";
	const PUSH_PROMPT_COOLDOWN_HOURS = 12;

	// Register service worker for Desk
	const registerServiceWorker = async () => {
		if (!("serviceWorker" in navigator)) {
			return null;
		}

		try {
			const registration = await navigator.serviceWorker.register("/assets/plasticflow/service-worker.js");
			return registration;
		} catch (error) {
			console.error("[PlasticFlow] Service worker registration failed:", error);
			return null;
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

	const urlBase64ToUint8Array = (base64String) => {
		const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
		const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");

		const rawData = window.atob(base64);
		const outputArray = new Uint8Array(rawData.length);

		for (let i = 0; i < rawData.length; ++i) {
			outputArray[i] = rawData.charCodeAt(i);
		}
		return outputArray;
	};

	const withinCooldown = () => {
		try {
			const lastPrompt = window.localStorage.getItem(PUSH_STORAGE_KEY);
			if (!lastPrompt) {
				return false;
			}
			const deltaHours = (Date.now() - Number(lastPrompt)) / (1000 * 60 * 60);
			return deltaHours < PUSH_PROMPT_COOLDOWN_HOURS;
		} catch (error) {
			console.warn("[PlasticFlow] Unable to read push prompt history:", error);
			return false;
		}
	};

	const markPrompt = () => {
		try {
			window.localStorage.setItem(PUSH_STORAGE_KEY, Date.now().toString());
		} catch (error) {
			console.warn("[PlasticFlow] Unable to persist push prompt timestamp:", error);
		}
	};

	const registerPushSubscription = async (registration) => {
		if (!registration || !("PushManager" in window) || !("Notification" in window)) {
			return;
		}
		if (!window.frappe || !window.frappe.session || window.frappe.session.user === "Guest") {
			return;
		}

		try {
			let permission = Notification.permission;
			if (permission === "default" && !withinCooldown()) {
				permission = await Notification.requestPermission();
				markPrompt();
			}

			if (permission !== "granted") {
				return;
			}

			const existing = await registration.pushManager.getSubscription();
			const { message: publicKey } = await frappe.call("plasticflow.notifications.push.get_vapid_public_key");
			const serverKey = urlBase64ToUint8Array(publicKey);

			let subscription = existing;
			if (!subscription) {
				subscription = await registration.pushManager.subscribe({
					userVisibleOnly: true,
					applicationServerKey: serverKey,
				});
			}

			await frappe.call("plasticflow.notifications.push.register_subscription", {
				subscription: subscription.toJSON(),
				device: window.navigator.userAgent,
				browser: window.navigator.userAgentData ? window.navigator.userAgentData.brands?.[0]?.brand : null,
			});
		} catch (error) {
			console.error("[PlasticFlow] Failed to register push subscription:", error);
		}
	};

	const setupServiceWorkerMessaging = () => {
		if (!("serviceWorker" in navigator)) {
			return;
		}

		navigator.serviceWorker.addEventListener("message", (event) => {
			if (!event.data || event.data.type !== "plasticflow.push.open") {
				return;
			}
			const { reference_doctype, reference_name } = event.data;
            if (reference_doctype && reference_name && window.frappe && frappe.set_route) {
                frappe.set_route("Form", reference_doctype, reference_name);
			} else if (window.frappe && frappe.set_route) {
				frappe.set_route("app");
			}
		});
	};

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", () => {
			ensureManifestLink();
			setupServiceWorkerMessaging();
			registerServiceWorker().then(registerPushSubscription);
		});
	} else {
		ensureManifestLink();
		setupServiceWorkerMessaging();
		registerServiceWorker().then(registerPushSubscription);
	}
})();
