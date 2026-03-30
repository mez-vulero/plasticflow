import frappe
import requests
import os

# Hardcoded Credentials
BOT_TOKEN = "5743451298"
CHAT_ID = "8234148975:AAF1LYfgYK_o-nyMCg1JcQG_hief5IM6M-A"

def send_file_to_telegram(doc, method=None):
    """
    Triggered after a new File record is inserted into the database.
    """
    # 1. Filter: Only send PDF files
    # This prevents sending every small thumbnail or system icon
    if not doc.file_name or not doc.file_name.lower().endswith(".pdf"):
        return

    try:
        # 2. Resolve the physical file path on the server
        # doc.file_url looks like "/files/my_invoice.pdf"
        file_path = frappe.get_site_path(doc.file_url.strip("/"))
        
        if not os.path.exists(file_path):
            # If the file hasn't hit the disk yet, we might need a tiny delay 
            # or to fetch content via frappe.get_doc
            frappe.log_error(f"File path {file_path} not found on disk.", "Telegram Upload")
            return

        # 3. Read the file binary
        with open(file_path, "rb") as f:
            pdf_content = f.read()

        # 4. Telegram API Request
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
        
        files = {
            'document': (doc.file_name, pdf_content, 'application/pdf')
        }
        
        # Build a helpful caption
        caption = f"📄 *New File Generated*\n"
        caption += f"*Name:* {doc.file_name}\n"
        if doc.attached_to_doctype:
            caption += f"*Linked to:* {doc.attached_to_doctype} ({doc.attached_to_name})"

        data = {
            'chat_id': CHAT_ID,
            'caption': caption,
            'parse_mode': 'Markdown'
        }

        # 5. Execute Request
        response = requests.post(url, data=data, files=files, timeout=30)
        
        if response.status_code != 200:
            frappe.log_error(f"Telegram API Error: {response.text}", "Telegram File Send")

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Telegram File Send Exception")