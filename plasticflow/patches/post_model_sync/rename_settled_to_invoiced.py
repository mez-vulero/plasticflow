import frappe


def execute():
	frappe.db.sql(
		"""UPDATE `tabSales Order` SET status = 'Invoiced' WHERE status = 'Settled'"""
	)
