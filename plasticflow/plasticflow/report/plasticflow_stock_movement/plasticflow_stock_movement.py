from __future__ import annotations

import frappe
from frappe import _


def execute(filters=None):
	filters = filters or {}
	from_date = filters.get("from_date")
	to_date = filters.get("to_date")

	conditions = ["last_movement is not null"]
	params = {}
	if from_date:
		conditions.append("last_movement >= %(from_date)s")
		params["from_date"] = from_date
	if to_date:
		conditions.append("last_movement <= %(to_date)s")
		params["to_date"] = to_date

	where_clause = f" where {' and '.join(conditions)}" if conditions else ""

	rows = frappe.db.sql(
		f"""
		select date(last_movement) as movement_date,
		       sum(reserved_qty) as reserved_qty,
		       sum(issued_qty) as issued_qty
		from `tabStock Ledger Entry`
		{where_clause}
		group by date(last_movement)
		order by movement_date
		""",
		params,
		as_dict=True,
	)

	columns = [
		{"label": _("Date"), "fieldname": "movement_date", "fieldtype": "Date", "width": 140},
		{"label": _("Reserved Qty"), "fieldname": "reserved_qty", "fieldtype": "Float", "width": 120},
		{"label": _("Issued Qty"), "fieldname": "issued_qty", "fieldtype": "Float", "width": 120},
	]

	data = rows

	labels = [row.movement_date for row in rows]
	chart = {
		"data": {
			"labels": labels,
			"datasets": [
				{"name": _("Reserved Qty"), "values": [float(row.reserved_qty or 0) for row in rows]},
				{"name": _("Issued Qty"), "values": [float(row.issued_qty or 0) for row in rows]},
			],
		},
		"type": "line",
	}

	return columns, data, None, chart
