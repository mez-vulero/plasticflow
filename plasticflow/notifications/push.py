from __future__ import annotations

import json
import frappe
from frappe import _
from frappe.utils import now_datetime, strip_html
from py_vapid import Vapid
from py_vapid.utils import b64urlencode
from pywebpush import WebPushException, webpush
from cryptography.hazmat.primitives import serialization

DEFAULT_SUBSCRIPTION_DOCTYPE = "Push Subscription"
LEGACY_SUBSCRIPTION_DOCTYPE = "Plasticflow Push Subscription"


def _resolve_subscription_doctype() -> str:
	if getattr(frappe.local, "plasticflow_subscription_doctype", None):
		return frappe.local.plasticflow_subscription_doctype
	for doctype in (DEFAULT_SUBSCRIPTION_DOCTYPE, LEGACY_SUBSCRIPTION_DOCTYPE):
		if frappe.db.exists("DocType", doctype):
			frappe.local.plasticflow_subscription_doctype = doctype
			return doctype
	frappe.throw(
		_("Push Subscription DocType is missing. Please run `bench migrate`."),
		title=_("Missing DocType"),
	)


def _get_vapid_claims() -> dict[str, str]:
	email = frappe.conf.get("plasticflow_vapid_email")
	if not email:
		email = frappe.db.get_single_value("System Settings", "email_footer_address") or "admin@localhost"
	return {"sub": f"mailto:{email}"}


def _get_vapid_keys(strict: bool = False) -> tuple[str | None, str | None]:
	public_key = frappe.conf.get("plasticflow_vapid_public_key")
	private_key = frappe.conf.get("plasticflow_vapid_private_key")
	if not public_key or not private_key:
		if strict:
			frappe.throw(
				_("VAPID keys are not configured. Please set `plasticflow_vapid_public_key` "
				"and `plasticflow_vapid_private_key` in site_config.json."),
				title=_("Push Notifications Disabled"),
			)
		return None, None
	return public_key, private_key


@frappe.whitelist()
def get_vapid_public_key() -> str:
	"""Expose the VAPID public key to the PWA client."""
	public_key, _ = _get_vapid_keys(strict=True)
	return public_key


@frappe.whitelist()
def register_subscription(subscription: str | dict, device: str | None = None, browser: str | None = None) -> dict:
	"""Persist a push subscription for the current user."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Login is required to enable push notifications."))

	if isinstance(subscription, str):
		subscription = json.loads(subscription)

	endpoint = subscription.get("endpoint")
	keys = subscription.get("keys", {})
	p256dh = keys.get("p256dh")
	auth = keys.get("auth")

	if not endpoint or not p256dh or not auth:
		frappe.throw(_("Invalid push subscription payload received."))

	doctype = _resolve_subscription_doctype()
	existing_name = frappe.db.get_value(doctype, {"endpoint": endpoint})

	values = {
		"user": frappe.session.user,
		"endpoint": endpoint,
		"p256dh": p256dh,
		"auth": auth,
		"device": device,
		"browser": browser,
		"is_active": 1,
		"last_failure": None,
		"failure_reason": None,
	}

	if existing_name:
		frappe.db.set_value(doctype, existing_name, values, update_modified=True)
		return {"subscription": existing_name}

	name = frappe.generate_hash(length=10)
	now = now_datetime()
	meta = {
		"name": name,
		"owner": frappe.session.user,
		"creation": now,
		"modified": now,
		"modified_by": frappe.session.user,
		"docstatus": 0,
		"idx": 0,
	}

	insert_values = {**meta, **values}
	columns = ", ".join(f"`{col}`" for col in insert_values)
	placeholders = ", ".join(["%s"] * len(insert_values))
	table = f"tab{doctype}"

	frappe.db.sql(
		f"insert into `{table}` ({columns}) values ({placeholders})",
		list(insert_values.values()),
	)

	return {"subscription": name}


def send_notification_to_user(
	user: str,
	title: str,
	body: str,
	reference_doctype: str | None = None,
	reference_name: str | None = None,
) -> None:
	"""Send a push notification to all active subscriptions for the user."""
	doctype = _resolve_subscription_doctype()
	subscriptions = frappe.get_all(
		doctype,
		filters={"user": user, "is_active": 1},
		fields=["name", "endpoint", "p256dh", "auth"],
	)
	if not subscriptions:
		return

	public_key, private_key = _get_vapid_keys()
	if not public_key or not private_key:
		return

	payload = {
		"title": title,
		"body": body,
		"reference_doctype": reference_doctype,
		"reference_name": reference_name,
	}

	claims = _get_vapid_claims()

	for sub in subscriptions:
		subscription_info = {
			"endpoint": sub.endpoint,
			"keys": {
				"p256dh": sub.p256dh,
				"auth": sub.auth,
			},
		}

		try:
			webpush(
				subscription_info=subscription_info,
				data=json.dumps(payload),
				vapid_private_key=private_key,
				vapid_claims=claims,
			)
		except WebPushException as exc:
			_handle_delivery_failure(sub.name, exc)
		except Exception as exc:  # noqa: BLE001 - best effort
			_handle_delivery_failure(sub.name, exc)
		else:
			_mark_delivery_success(sub.name)


def _mark_delivery_success(docname: str) -> None:
	doctype = _resolve_subscription_doctype()
	frappe.db.set_value(
		doctype,
		docname,
		{
			"last_success": now_datetime(),
			"last_failure": None,
			"failure_reason": None,
			"is_active": 1,
		},
		update_modified=False,
	)



def _handle_delivery_failure(docname: str, exc: Exception) -> None:
	status = getattr(getattr(exc, "response", None), "status_code", None)
	disable = status in {404, 410}  # Subscription expired or gone

	doctype = _resolve_subscription_doctype()
	frappe.db.set_value(
		doctype,
		docname,
		{
			"last_failure": now_datetime(),
			"failure_reason": str(exc),
			"is_active": 0 if disable else 1,
		},
		update_modified=False,
	)


def handle_notification_log(doc, method=None):
	"""Doc event hook: push out system notifications."""
	if not getattr(doc, "for_user", None):
		return
	if doc.type and doc.type.upper() == "DEFAULT":  # Nothing to notify
		return

	title = doc.subject or _("Notification")
	body = (doc.email_content or getattr(doc, "subject", "") or "")
	body = strip_html(body) if body else _("You have a new notification.")

	send_notification_to_user(
		user=doc.for_user,
		title=title,
		body=body,
		reference_doctype=doc.document_type,
		reference_name=doc.document_name,
	)


def generate_vapid_keys() -> dict[str, str]:
	"""Utility to create a VAPID key pair for site administrators."""
	vapid = Vapid()
	vapid.generate_keys()
	private_number = vapid.private_key.private_numbers().private_value
	private_bytes = private_number.to_bytes(32, byteorder="big")
	public_bytes = vapid.public_key.public_bytes(
		encoding=serialization.Encoding.X962,
		format=serialization.PublicFormat.UncompressedPoint,
	)
	return {
		"public_key": b64urlencode(public_bytes),
		"private_key": b64urlencode(private_bytes),
	}
