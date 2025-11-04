import frappe


def execute():
	rename_map = {
		"Stock Batch": "Stock Entries",
		"Stock Batch Item": "Stock Entry Items",
	}

	for old, new in rename_map.items():
		if not frappe.db.exists("DocType", old):
			continue
		if frappe.db.exists("DocType", new):
			continue
		frappe.rename_doc("DocType", old, new, force=True)

	# rename child table references in field definitions
	frappe.db.sql(
		"""
		update `tabDocField`
		set options = 'Stock Entries'
		where options = 'Stock Batch'
	"""
	)
	frappe.db.sql(
		"""
		update `tabDocField`
		set options = 'Stock Entry Items'
		where options = 'Stock Batch Item'
	"""
	)
