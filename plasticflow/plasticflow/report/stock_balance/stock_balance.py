from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_days, get_datetime


def execute(filters=None):
	filters = filters or {}
	import_shipment = filters.get("import_shipment")
	warehouse = filters.get("warehouse")
	as_of_date = filters.get("as_of_date")

	conditions = ["1=1"]
	params = {}

	if import_shipment:
		conditions.append("import_shipment = %(import_shipment)s")
		params["import_shipment"] = import_shipment
	if warehouse:
		conditions.append("warehouse = %(warehouse)s")
		params["warehouse"] = warehouse

	if as_of_date:
		as_of_end = add_days(get_datetime(as_of_date), 1)
		params["as_of_end"] = as_of_end
		if frappe.db.table_exists("Stock Ledger Movement"):
			conditions.append("movement_datetime < %(as_of_end)s")
			where_clause = " and ".join(conditions)
			rows = frappe.db.sql(
				f"""
				select
					product,
					import_shipment,
					location_type,
					warehouse,
					sum(available_delta) as available_qty,
					sum(reserved_delta) as reserved_qty,
					sum(issued_delta) as issued_qty,
					max(movement_datetime) as last_movement
				from `tabStock Ledger Movement`
				where {where_clause}
				group by product, import_shipment, location_type, warehouse
				order by product, import_shipment, location_type, warehouse
				""",
				params,
				as_dict=True,
			)
		else:
			conditions.append("coalesce(last_movement, creation) < %(as_of_end)s")
			where_clause = " and ".join(conditions)
			rows = frappe.db.sql(
				f"""
				select
					product,
					import_shipment,
					location_type,
					warehouse,
					sum(available_qty) as available_qty,
					sum(reserved_qty) as reserved_qty,
					sum(issued_qty) as issued_qty,
					max(last_movement) as last_movement
				from `tabStock Ledger Entry`
				where {where_clause}
				group by product, import_shipment, location_type, warehouse
				order by product, import_shipment, location_type, warehouse
				""",
				params,
				as_dict=True,
			)
	else:
		where_clause = " and ".join(conditions)
		rows = frappe.db.sql(
			f"""
			select
				product,
				import_shipment,
				location_type,
				warehouse,
				sum(available_qty) as available_qty,
				sum(reserved_qty) as reserved_qty,
				sum(issued_qty) as issued_qty,
				max(last_movement) as last_movement
			from `tabStock Ledger Entry`
			where {where_clause}
			group by product, import_shipment, location_type, warehouse
			order by product, import_shipment, location_type, warehouse
			""",
			params,
			as_dict=True,
		)

	columns = [
		{"label": _("Product"), "fieldname": "product", "fieldtype": "Link", "options": "Product", "width": 200},
		{
			"label": _("Import Shipment"),
			"fieldname": "import_shipment",
			"fieldtype": "Link",
			"options": "Import Shipment",
			"width": 160,
		},
		{"label": _("Location Type"), "fieldname": "location_type", "fieldtype": "Data", "width": 120},
		{"label": _("Warehouse"), "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 160},
		{"label": _("Available Qty"), "fieldname": "available_qty", "fieldtype": "Float", "width": 130},
		{"label": _("Reserved Qty"), "fieldname": "reserved_qty", "fieldtype": "Float", "width": 130},
		{"label": _("Issued Qty"), "fieldname": "issued_qty", "fieldtype": "Float", "width": 120},
		{"label": _("Last Movement"), "fieldname": "last_movement", "fieldtype": "Datetime", "width": 170},
	]

	return columns, rows, None, None
