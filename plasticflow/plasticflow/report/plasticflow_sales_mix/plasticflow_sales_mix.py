from __future__ import annotations

import frappe
from frappe import _


def execute(filters=None):
	rows = frappe.db.sql(
		"""
		select sales_type, sum(total_amount) as total_amount
		from `tabSales Order`
		where docstatus = 1
		group by sales_type
		""",
		as_dict=True,
	)

	columns = [
		{"label": _("Sales Type"), "fieldname": "sales_type", "fieldtype": "Data", "width": 180},
		{"label": _("Total Amount"), "fieldname": "total_amount", "fieldtype": "Currency", "width": 160},
	]

	data = rows

	chart = {
		"data": {
			"labels": [row.sales_type or _("Unknown") for row in rows],
			"datasets": [{"values": [float(row.total_amount or 0) for row in rows]}],
		},
		"type": "donut",
	}

	return columns, data, None, chart
