from __future__ import annotations

import frappe
from frappe import _


def execute(filters=None):
	filters = filters or {}

	conditions = ["docstatus = 1"]
	params = {}

	from_date = filters.get("from_date")
	to_date = filters.get("to_date")
	status = filters.get("status")

	if from_date:
		conditions.append("order_date >= %(from_date)s")
		params["from_date"] = from_date
	if to_date:
		conditions.append("order_date <= %(to_date)s")
		params["to_date"] = to_date
	if status:
		conditions.append("status = %(status)s")
		params["status"] = status

	where_clause = f"where {' and '.join(conditions)}" if conditions else ""

	rows = frappe.db.sql(
		f"""
		select status, count(*) as total
		from `tabSales Order`
		{where_clause}
		group by status
		order by count(*) desc
		""",
		params,
		as_dict=True,
	)

	columns = [
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 200},
		{"label": _("Orders"), "fieldname": "total", "fieldtype": "Int", "width": 120},
	]

	data = rows

	chart = {
		"data": {
			"labels": [row.status or _("Unknown") for row in rows],
			"datasets": [{"values": [row.total for row in rows]}],
		},
		"type": "donut",
	}

	return columns, data, None, chart
