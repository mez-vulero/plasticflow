import frappe
import requests
from frappe import _

# Hardcoded Credentials
BOT_TOKEN = "5743451298"
CHAT_ID = "8234148975:AAF1LYfgYK_o-nyMCg1JcQG_hief5IM6M-A"

def send_pdf_on_save(doc, method=None):
    """
    Generates a PDF of the current document and sends it to Telegram.
    """
    # 1. Check if the document is new or being updated
    # (Optional: Only send if it's the first save, or every save)
    
    try:
        # 2. Generate PDF using the default print format
        # If you want a specific format, add: print_format="My Format Name"
        pdf_content = frappe.get_print(doc.doctype, doc.name, as_pdf=True)
        
        # 3. Prepare Telegram API
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
        
        files = {
            'document': (f"{doc.name}.pdf", pdf_content, 'application/pdf')
        }
        
        caption = f"💾 *Document Saved*\n"
        caption += f"*Type:* {doc.doctype}\n"
        caption += f"*ID:* {doc.name}"

        data = {
            'chat_id': CHAT_ID,
            'caption': caption,
            'parse_mode': 'Markdown'
        }

        # 4. Send via Background Job (Recommended so the UI doesn't hang)
        # We use a separate function for the actual POST request to keep 'Save' fast
        frappe.enqueue(
            method=execute_telegram_request,
            url=url,
            data=data,
            files=files,
            queue='short'
        )

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Telegram PDF Save Hook Failed")

def execute_telegram_request(url, data, files):
    """Helper to execute the POST request in the background"""
    response = requests.post(url, data=data, files=files, timeout=30)
    if response.status_code != 200:
        frappe.log_error(f"Telegram API Error: {response.text}", "Telegram POST Failed")