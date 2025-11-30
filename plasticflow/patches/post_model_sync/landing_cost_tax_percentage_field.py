import frappe


def execute():
	frappe.reload_doc("plasticflow", "doctype", "landing_cost_tax")
	# Rename amount column to percentage (float) while preserving values
	if frappe.db.has_column("Landing Cost Tax", "amount") and not frappe.db.has_column("Landing Cost Tax", "percentage"):
		frappe.db.sql_ddl("alter table `tabLanding Cost Tax` change column `amount` `percentage` decimal(18,6) null")
