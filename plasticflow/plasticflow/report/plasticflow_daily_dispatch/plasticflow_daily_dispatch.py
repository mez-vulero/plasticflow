from __future__ import annotations

import frappe
from frappe import _


def execute(filters=None):
	filters = filters or {}
	from_date = filters.get("from_date")
	to_date = filters.get("to_date")

	conditions = []
	params = {}
	if from_date:
		conditions.append("date(generated_on) >= %(from_date)s")
		params["from_date"] = from_date
	if to_date:
		conditions.append("date(generated_on) <= %(to_date)s")
		params["to_date"] = to_date

	where_clause = f"where {' and '.join(conditions)}" if conditions else ""

	rows = frappe.db.sql(
		f"""
		select date(generated_on) as dispatch_date, count(*) as gate_pass_count
		from `tabGate Pass`
		{where_clause}
		group by date(generated_on)
		order by dispatch_date
		""",
		params,
		as_dict=True,
	)

	columns = [
		{"label": _("Date"), "fieldname": "dispatch_date", "fieldtype": "Date", "width": 150},
		{"label": _("Gate Passes"), "fieldname": "gate_pass_count", "fieldtype": "Int", "width": 150},
	]

	chart = {
		"data": {
			"labels": [row.dispatch_date for row in rows],
			"datasets": [
				{
					"name": _("Gate Passes"),
					"values": [row.gate_pass_count for row in rows],
				}
			],
		},
		"type": "line",
	}

	return columns, rows, None, chart
