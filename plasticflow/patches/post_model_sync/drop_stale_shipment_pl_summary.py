import frappe


def execute():
	"""The report was originally named 'Shipment P/L Summary' — the slash breaks
	module resolution (frappe.scrub keeps '/'). Drop the stale DB row so the
	renamed 'Shipment PL Summary' takes over on this migrate.
	"""
	stale = "Shipment P/L Summary"
	if frappe.db.exists("Report", stale):
		frappe.db.delete("Has Role", {"parent": stale, "parenttype": "Report"})
		frappe.db.delete("Report", {"name": stale})
		frappe.db.commit()
