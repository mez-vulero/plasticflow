import frappe


def execute():
	"""Remove legacy Customs Entry doctypes and tables from live sites."""
	if frappe.db.table_exists("Customs Documents"):
		frappe.db.delete("Customs Documents", {"parenttype": "Customs Entry"})

	for doctype in ("Customs Entry Item", "Customs Entry"):
		if frappe.db.exists("DocType", doctype):
			frappe.delete_doc("DocType", doctype, ignore_permissions=True, force=1)

	for table in ("Customs Entry Item", "Customs Entry"):
		if frappe.db.table_exists(table):
			frappe.db.sql_ddl(f"drop table if exists `tab{table}`")
