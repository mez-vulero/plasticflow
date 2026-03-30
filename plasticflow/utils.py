import frappe
import requests
from frappe import _

# Hardcoded Credentials (Fixed Order)
BOT_TOKEN = "8234148975:AAF1LYfgYK_o-nyMCg1JcQG_hief5IM6M-A"
CHAT_ID = "5743451298"

def send_pdf_on_save(doc, method=None):
    """
    Triggered by hooks.py. 
    Generates a PDF and sends it via Telegram in the background.
    """
    try:
        # Crucial: Ensure the document is fully loaded in the DB 
        # before generating the PDF to avoid missing items/totals
        doc.reload()

        # 1. Generate PDF binary using default print format
        pdf_content = frappe.get_print(doc.doctype, doc.name, as_pdf=True)
        
        # 2. Prepare API URL and Data
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
        
        files = {
            'document': (f"{doc.name}.pdf", pdf_content, 'application/pdf')
        }
        
        
        caption = f"*Gate Pass for:* {doc.customer_name}"
        caption += f"*Plate Number:* {doc.plate_number}\n"

        data = {
            'chat_id': CHAT_ID,
            'caption': caption,
            'parse_mode': 'Markdown'
        }

        # 3. Hand off to Background Worker
        # REPLACE 'your_app' with your actual app name folder
        frappe.enqueue(
            method="plasticflow.utils.execute_telegram_request",
            url=url,
            data=data,
            files=files,
            queue='short'
        )

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Telegram PDF Notification Failed")

def execute_telegram_request(url, data, files):
    """
    Background worker function that performs the actual upload.
    """
    try:
        response = requests.post(url, data=data, files=files, timeout=30)
        if response.status_code != 200:
            frappe.log_error(f"Telegram API Error: {response.text}", "Telegram POST Failed")
    except Exception as e:
        frappe.log_error(str(e), "Telegram Connection Error")