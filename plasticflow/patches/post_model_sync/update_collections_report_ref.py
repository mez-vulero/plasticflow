import frappe


def execute():
	if not frappe.db.exists("Report", "Plasticflow Collections Timeline"):
		return

	report = frappe.get_doc("Report", "Plasticflow Collections Timeline")
	if report.ref_doctype != "Invoice":
		report.ref_doctype = "Invoice"
		# ensure permissions align with parent doctype for charts/workspaces
		report.save(ignore_permissions=True)
