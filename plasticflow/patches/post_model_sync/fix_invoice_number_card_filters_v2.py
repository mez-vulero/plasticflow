import frappe


UPDATES = {
	"Overdue Credit Invoices": {
		"filters_json": (
			'[["Invoice","docstatus","=",1],'
			'["Invoice","invoice_type","=","Credit"],'
			'["Invoice","outstanding_amount",">",0]]'
		),
		"dynamic_filters_json": '[["Invoice","due_date","<","frappe.datetime.nowdate()"]]',
	},
	"Overdue Receivables": {
		"filters_json": (
			'[["Invoice","docstatus","=",1],'
			'["Invoice","outstanding_amount",">",0]]'
		),
		"dynamic_filters_json": '[["Invoice","due_date","<","frappe.datetime.nowdate()"]]',
	},
	"Unpaid Credit Invoices": {
		"filters_json": (
			'[["Invoice","docstatus","=",1],'
			'["Invoice","invoice_type","=","Credit"],'
			'["Invoice","outstanding_amount",">",0]]'
		),
		"dynamic_filters_json": "[]",
	},
}


def execute():
	"""Invoice.status field was removed; rebuild overdue/unpaid number card filters.

	Overdue = outstanding > 0 AND due_date < today. The today comparison cannot live
	in filters_json (server tries to parse "Today" as a literal date string and fails),
	so the due_date filter goes in dynamic_filters_json where the client evaluates
	frappe.datetime.nowdate() at render time.
	"""
	for name, fields in UPDATES.items():
		if frappe.db.exists("Number Card", name):
			frappe.db.set_value("Number Card", name, fields, update_modified=False)
	frappe.db.commit()
	frappe.clear_cache()
