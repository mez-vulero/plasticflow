from __future__ import annotations

import frappe
from frappe import _


def execute(filters=None):
	limit = frappe.utils.cint((filters or {}).get("limit") or 5)

	rows = frappe.db.sql(
		"""
		select product, sum(available_qty) as available_qty
		from `tabPlasticflow Stock Ledger Entry`
		where product is not null
		group by product
		order by available_qty desc
		limit %(limit)s
		""",
		{"limit": limit},
		as_dict=True,
	)

	columns = [
		{"label": _("Product"), "fieldname": "product", "fieldtype": "Link", "options": "Product", "width": 220},
		{"label": _("Available Qty"), "fieldname": "available_qty", "fieldtype": "Float", "width": 140},
	]

	data = rows

	chart = {
		"data": {
			"labels": [row.product for row in rows],
			"datasets": [{"name": _("Available Qty"), "values": [float(row.available_qty or 0) for row in rows]}],
		},
		"type": "bar",
	}

	return columns, data, None, chart
