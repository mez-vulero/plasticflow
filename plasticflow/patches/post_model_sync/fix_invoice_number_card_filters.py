import frappe


NEW_FILTERS = {
	"Overdue Credit Invoices": (
		'[["Invoice","docstatus","=",1],'
		'["Invoice","invoice_type","=","Credit"],'
		'["Invoice","outstanding_amount",">",0],'
		'["Invoice","due_date","<","Today"]]'
	),
	"Overdue Receivables": (
		'[["Invoice","docstatus","=",1],'
		'["Invoice","outstanding_amount",">",0],'
		'["Invoice","due_date","<","Today"]]'
	),
	"Unpaid Credit Invoices": (
		'[["Invoice","docstatus","=",1],'
		'["Invoice","invoice_type","=","Credit"],'
		'["Invoice","outstanding_amount",">",0]]'
	),
}


def execute():
	"""Invoice.status field was removed; update number cards that still filter on it."""
	for name, filters_json in NEW_FILTERS.items():
		if frappe.db.exists("Number Card", name):
			frappe.db.set_value(
				"Number Card", name, "filters_json", filters_json, update_modified=False
			)
	frappe.db.commit()
	frappe.clear_cache()
