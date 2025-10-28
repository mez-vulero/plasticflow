import frappe


def execute():
	rename_map = {
		"Stock Batch": "Plasticflow Stock Entry",
		"Stock Batch Item": "Plasticflow Stock Entry Item",
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
		set options = 'Plasticflow Stock Entry'
		where options = 'Stock Batch'
	"""
	)
	frappe.db.sql(
		"""
		update `tabDocField`
		set options = 'Plasticflow Stock Entry Item'
		where options = 'Stock Batch Item'
	"""
	)
