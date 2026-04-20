import frappe
import requests
from frappe import _


def _get_telegram_config():
	"""Return (bot_token, chat_id) from PlasticFlow Telegram Settings or None if disabled."""
	try:
		settings = frappe.get_cached_doc("PlasticFlow Telegram Settings")
	except frappe.DoesNotExistError:
		return None

	if not settings.enabled:
		return None

	try:
		bot_token = settings.get_password("bot_token")
	except Exception:
		# Encryption key mismatch or other decryption failure — disable silently.
		frappe.log_error(frappe.get_traceback(), "PlasticFlow Telegram bot_token decrypt failed")
		return None

	chat_id = settings.chat_id

	if not bot_token or not chat_id:
		return None

	return bot_token, chat_id


def send_pdf_on_save(doc, method=None):
	"""
	Triggered by hooks.py on Gate Pass after_insert/on_update.
	Generates a PDF and sends it via Telegram in the background.
	"""
	config = _get_telegram_config()
	if not config:
		return

	bot_token, chat_id = config

	try:
		doc.reload()

		pdf_content = frappe.get_print(doc.doctype, doc.name, as_pdf=True)

		url = f"https://api.telegram.org/bot{bot_token}/sendDocument"

		files = {
			"document": (f"{doc.name}.pdf", pdf_content, "application/pdf"),
		}

		caption = f"*Gate Pass for:* {doc.customer_name}\n"
		caption += f"*Plate Number:* {doc.plate_number}"

		data = {
			"chat_id": chat_id,
			"caption": caption,
			"parse_mode": "Markdown",
		}

		frappe.enqueue(
			method="plasticflow.utils.execute_telegram_request",
			url=url,
			data=data,
			files=files,
			queue="short",
		)

	except Exception:
		frappe.log_error(frappe.get_traceback(), "Telegram PDF Notification Failed")


def execute_telegram_request(url, data, files):
	"""Background worker function that performs the actual upload."""
	try:
		response = requests.post(url, data=data, files=files, timeout=30)
		if response.status_code != 200:
			frappe.log_error(f"Telegram API Error: {response.text}", "Telegram POST Failed")
	except Exception as e:
		frappe.log_error(str(e), "Telegram Connection Error")
