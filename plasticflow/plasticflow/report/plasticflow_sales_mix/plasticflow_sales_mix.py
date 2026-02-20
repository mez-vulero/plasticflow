from __future__ import annotations

import frappe
from frappe import _


def execute(filters=None):
	filters = filters or {}
	conditions = ["docstatus = 1"]
	params = {}

	from_date = filters.get("from_date")
	to_date = filters.get("to_date")
	sales_type = filters.get("sales_type")

	if from_date:
		conditions.append("order_date >= %(from_date)s")
		params["from_date"] = from_date
	if to_date:
		conditions.append("order_date <= %(to_date)s")
		params["to_date"] = to_date
	if sales_type:
		conditions.append("sales_type = %(sales_type)s")
		params["sales_type"] = sales_type

	where_clause = f"where {' and '.join(conditions)}" if conditions else ""

	rows = frappe.db.sql(
		f"""
		select sales_type, sum(total_amount) as total_amount
		from `tabSales Order`
		{where_clause}
		group by sales_type
		""",
		params,
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
