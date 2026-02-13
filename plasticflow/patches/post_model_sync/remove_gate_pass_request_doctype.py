import frappe


def execute():
	if frappe.db.exists("DocType", "Gate Pass Request"):
		frappe.delete_doc("DocType", "Gate Pass Request", ignore_permissions=True, force=True)
