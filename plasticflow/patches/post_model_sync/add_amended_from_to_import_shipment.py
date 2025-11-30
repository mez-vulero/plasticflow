import frappe


def execute():
	# Ensure schema matches DocType (is_submittable adds amended_from)
	frappe.reload_doc("plasticflow", "doctype", "import_shipment")

	if frappe.db.has_column("Import Shipment", "amended_from"):
		return

	# Add the standard amended_from link column for submittable doctypes.
	# Using raw SQL for compatibility across database backends.
	frappe.db.sql("ALTER TABLE `tabImport Shipment` ADD COLUMN `amended_from` varchar(140)")
