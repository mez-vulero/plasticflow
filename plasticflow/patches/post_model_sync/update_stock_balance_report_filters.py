import frappe


def execute():
	if not frappe.db.exists("Report", "Stock Balance"):
		return

	report = frappe.get_doc("Report", "Stock Balance")
	report.filters = [
		{
			"fieldname": "import_shipment",
			"fieldtype": "Link",
			"label": "Import Shipment",
			"options": "Import Shipment",
		},
		{
			"fieldname": "warehouse",
			"fieldtype": "Link",
			"label": "Warehouse",
			"options": "Warehouse",
		},
		{
			"default": "Kg",
			"fieldname": "display_uom",
			"fieldtype": "Select",
			"label": "Display UOM",
			"options": "\nKg\nTon",
		},
		{
			"fieldname": "as_of_date",
			"fieldtype": "Date",
			"label": "As Of Date",
		},
	]
	report.save(ignore_permissions=True)
