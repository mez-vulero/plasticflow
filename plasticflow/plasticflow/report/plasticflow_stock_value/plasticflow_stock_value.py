from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = filters or {}
	product = filters.get("product")
	import_shipment = filters.get("import_shipment")
	location_type = filters.get("location_type")
	warehouse = filters.get("warehouse")

	conditions = ["1=1"]
	params = {}
	if product:
		conditions.append("product = %(product)s")
		params["product"] = product
	if import_shipment:
		conditions.append("import_shipment = %(import_shipment)s")
		params["import_shipment"] = import_shipment
	if location_type:
		conditions.append("location_type = %(location_type)s")
		params["location_type"] = location_type
	if warehouse:
		conditions.append("warehouse = %(warehouse)s")
		params["warehouse"] = warehouse

	where_clause = " and ".join(conditions)

	rows = frappe.db.sql(
		f"""
		select
			product,
			sum(case when location_type = 'Customs' then available_qty else 0 end) as customs_qty,
			sum(case when location_type = 'Warehouse' then available_qty else 0 end) as warehouse_qty,
			sum(case when location_type = 'Customs' then available_qty * coalesce(landed_cost_rate, 0) else 0 end) as customs_value,
			sum(case when location_type = 'Warehouse' then available_qty * coalesce(landed_cost_rate, 0) else 0 end) as warehouse_value,
			sum(available_qty * coalesce(landed_cost_rate, 0)) as total_value,
			max(last_movement) as last_movement
		from `tabStock Ledger Entry`
		where {where_clause}
		group by product
		order by product
		""",
		params,
		as_dict=True,
	)

	columns = [
		{"label": _("Product"), "fieldname": "product", "fieldtype": "Link", "options": "Product", "width": 200},
		{"label": _("Customs Qty"), "fieldname": "customs_qty", "fieldtype": "Float", "width": 130},
		{"label": _("Warehouse Qty"), "fieldname": "warehouse_qty", "fieldtype": "Float", "width": 140},
		{"label": _("Customs Value"), "fieldname": "customs_value", "fieldtype": "Currency", "width": 140},
		{"label": _("Warehouse Value"), "fieldname": "warehouse_value", "fieldtype": "Currency", "width": 150},
		{"label": _("Total Value"), "fieldname": "total_value", "fieldtype": "Currency", "width": 140},
		{"label": _("Last Movement"), "fieldname": "last_movement", "fieldtype": "Datetime", "width": 170},
	]

	chart = None
	if rows:
		labels = [row.product for row in rows]
		customs_values = [flt(row.customs_value or 0) for row in rows]
		warehouse_values = [flt(row.warehouse_value or 0) for row in rows]
		chart = {
			"data": {
				"labels": labels,
				"datasets": [
					{"name": _("Customs Value"), "values": customs_values},
					{"name": _("Warehouse Value"), "values": warehouse_values},
				],
			},
			"type": "bar",
			"stacked": 1,
		}

	return columns, rows, None, chart
