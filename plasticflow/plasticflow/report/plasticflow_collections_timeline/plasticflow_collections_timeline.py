from __future__ import annotations

import frappe
from frappe import _


def execute(filters=None):
	filters = filters or {}
	from_date = filters.get("from_date")
	to_date = filters.get("to_date")

	conditions = ["ps.parenttype = 'Sales Order'"]
	params = {}
	if from_date:
		conditions.append("ps.date_uploaded >= %(from_date)s")
		params["from_date"] = from_date
	if to_date:
		conditions.append("ps.date_uploaded <= %(to_date)s")
		params["to_date"] = to_date

	where_clause = f" where {' and '.join(conditions)}" if conditions else ""

	rows = frappe.db.sql(
		f"""
		select ps.date_uploaded as payment_date,
		       sum(ps.amount_paid) as amount_paid
		from `tabPayment Slips` ps
		left join `tabSales Order` so on so.name = ps.parent
		{where_clause}
		group by ps.date_uploaded
		order by payment_date
		""",
		params,
		as_dict=True,
	)

	columns = [
		{"label": _("Payment Date"), "fieldname": "payment_date", "fieldtype": "Date", "width": 140},
		{"label": _("Amount Collected"), "fieldname": "amount_paid", "fieldtype": "Currency", "width": 160},
	]

	data = rows

	chart = {
		"data": {
			"labels": [row.payment_date for row in rows],
			"datasets": [
				{
					"name": _("Amount Collected"),
					"values": [float(row.amount_paid or 0) for row in rows],
				}
			],
		},
		"type": "line",
	}

	return columns, data, None, chart
