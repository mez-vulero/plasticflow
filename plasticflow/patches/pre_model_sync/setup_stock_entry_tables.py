import frappe


def execute():
	frappe.reload_doc("plasticflow", "doctype", "stock_entries")
	frappe.reload_doc("plasticflow", "doctype", "stock_entry_items")
