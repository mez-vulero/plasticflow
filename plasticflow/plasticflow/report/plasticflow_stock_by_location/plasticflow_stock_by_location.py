from __future__ import annotations

import frappe
from frappe import _


def execute(filters=None):
	filters = filters or {}
	product = filters.get("product")

	conditions = []
	params = {}
	if product:
		conditions.append("product = %(product)s")
		params["product"] = product

	where_clause = f"where {' and '.join(conditions)}" if conditions else ""

	rows = frappe.db.sql(
		f"""
		select product, location_type, sum(available_qty) as available_qty
		from `tabPlasticflow Stock Ledger Entry`
		{where_clause}
		group by product, location_type
		""",
		params,
		as_dict=True,
	)

	location_summary = {"Customs": 0, "Warehouse": 0}
	for row in rows:
		location_summary[row.location_type] = float(row.available_qty or 0)

	product_label = product or _("All Products")
	data = [
		{"product": product_label, "location_type": location, "available_qty": qty}
		for location, qty in location_summary.items()
	]

	columns = [
		{"label": _("Product"), "fieldname": "product", "fieldtype": "Data", "width": 200},
		{"label": _("Location"), "fieldname": "location_type", "fieldtype": "Data", "width": 150},
		{"label": _("Available Qty"), "fieldname": "available_qty", "fieldtype": "Float", "width": 150},
	]

	chart = {
		"data": {
			"labels": list(location_summary.keys()),
			"datasets": [
				{
					"name": _("Available Qty"),
					"values": [location_summary["Customs"], location_summary["Warehouse"]],
				}
			],
		},
		"type": "bar",
	}

	return columns, data, None, chart
