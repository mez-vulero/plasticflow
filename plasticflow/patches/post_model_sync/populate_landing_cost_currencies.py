import frappe


def execute():
	update_allocation_rows()
	update_product_summary_rows()


def update_allocation_rows():
	rows = frappe.get_all(
		"Landing Cost Allocation",
		fields=["name", "parent"],
	)
	parents = {}
	for row in rows:
		parent = parents.get(row.parent)
		if parent is None:
			parent = frappe.db.get_value(
				"Landing Cost Worksheet",
				row.parent,
				"shipment_currency",
			)
			parents[row.parent] = parent
		if not parent:
			continue
		frappe.db.set_value(
			"Landing Cost Allocation",
			row.name,
			"import_currency",
			parent,
			update_modified=False,
		)


def update_product_summary_rows():
	rows = frappe.get_all(
		"Landing Cost Product Summary",
		fields=["name", "parent"],
	)
	parents = {}
	for row in rows:
		parent = parents.get(row.parent)
		if parent is None:
			parent = frappe.db.get_value(
				"Landing Cost Worksheet",
				row.parent,
				"shipment_currency",
			)
			parents[row.parent] = parent
		if not parent:
			continue
		frappe.db.set_value(
			"Landing Cost Product Summary",
			row.name,
			"import_currency",
			parent,
			update_modified=False,
		)
