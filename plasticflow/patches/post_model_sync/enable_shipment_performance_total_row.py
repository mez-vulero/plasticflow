import frappe


def execute():
	"""Force add_total_row=1 on Shipment Performance — the JSON change is
	ignored by migrate when the DB row's modified timestamp is newer."""
	if frappe.db.exists("Report", "Shipment Performance"):
		frappe.db.set_value(
			"Report",
			"Shipment Performance",
			"add_total_row",
			1,
			update_modified=False,
		)
		frappe.db.commit()
		frappe.clear_cache(doctype="Report")
