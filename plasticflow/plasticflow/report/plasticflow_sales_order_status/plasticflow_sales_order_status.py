from __future__ import annotations

import frappe
from frappe import _


def execute(filters=None):
	filters = filters or {}

	rows = frappe.db.sql(
		"""
		select status, count(*) as total
		from `tabSales Order`
		where docstatus = 1
		group by status
		order by count(*) desc
		""",
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
