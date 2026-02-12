import frappe


def execute():
	"""Ensure Sales Order Item uses row form (not editable grid)."""
	if not frappe.db.exists("DocType", "Sales Order Item"):
		return
	frappe.db.set_value("DocType", "Sales Order Item", "editable_grid", 0)
	frappe.db.delete("Property Setter", {"doc_type": "Sales Order Item", "property": "editable_grid"})
	frappe.clear_cache(doctype="Sales Order Item")
