import frappe


def execute():
	# Drop legacy payment_status column from Sales Order if present
	if frappe.db.has_column("Sales Order", "payment_status"):
		frappe.db.sql("alter table `tabSales Order` drop column payment_status")

	# Remove legacy Gate Pass doctypes if they still exist
	for doctype in ("Gate Pass Item", "Gate Pass"):
		if frappe.db.table_exists(f"tab{doctype}"):
			frappe.db.sql(f"drop table `tab{doctype}`")
