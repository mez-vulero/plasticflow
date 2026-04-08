import frappe


def execute():
	if frappe.db.has_column("Invoice", "status"):
		frappe.db.sql_ddl("ALTER TABLE `tabInvoice` DROP COLUMN `status`")
