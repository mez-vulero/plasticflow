import frappe
from frappe.model.rename_doc import rename_doc


def execute():
	old_name = "Plasticflow Stock Balance"
	new_name = "Stock Balance"

	if not frappe.db.exists("Report", old_name):
		return
	if frappe.db.exists("Report", new_name):
		return

	rename_doc("Report", old_name, new_name, force=True, ignore_permissions=True)
	report = frappe.get_doc("Report", new_name)
	if report.report_name != new_name:
		report.report_name = new_name
		report.save(ignore_permissions=True)
