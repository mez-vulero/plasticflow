from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_days, get_datetime, flt

from plasticflow.stock import uom as stock_uom


def execute(filters=None):
	filters = filters or {}
	import_shipment = filters.get("import_shipment")
	warehouse = filters.get("warehouse")
	as_of_date = filters.get("as_of_date")
	display_uom = (filters.get("display_uom") or "Kg").strip()

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
					sum(available_delta) as available_qty,
					sum(reserved_delta) as reserved_qty,
					sum(issued_delta) as issued_qty,
					max(movement_datetime) as last_movement
				from `tabStock Ledger Movement`
				where {where_clause}
				group by product
				order by product
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
					sum(available_qty) as available_qty,
					sum(reserved_qty) as reserved_qty,
					sum(issued_qty) as issued_qty,
					max(last_movement) as last_movement
				from `tabStock Ledger Entry`
				where {where_clause}
				group by product
				order by product
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
				sum(available_qty) as available_qty,
				sum(reserved_qty) as reserved_qty,
				sum(issued_qty) as issued_qty,
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
		{"label": _("UOM"), "fieldname": "uom", "fieldtype": "Data", "width": 90},
		{"label": _("Available Qty"), "fieldname": "available_qty", "fieldtype": "Float", "width": 130},
		{"label": _("Reserved Qty"), "fieldname": "reserved_qty", "fieldtype": "Float", "width": 130},
		{"label": _("Issued Qty"), "fieldname": "issued_qty", "fieldtype": "Float", "width": 120},
		{"label": _("Last Movement"), "fieldname": "last_movement", "fieldtype": "Datetime", "width": 170},
	]

	if not rows:
		return columns, rows, None, None

	product_codes = [row.product for row in rows if row.get("product")]
	product_uoms = {}
	if product_codes:
		for prod in frappe.db.get_all("Product", filters={"name": ["in", product_codes]}, fields=["name", "uom"]):
			product_uoms[prod.name] = prod.uom

	display_is_kg_ton = stock_uom.is_kg_uom(display_uom) or stock_uom.is_ton_uom(display_uom)

	for row in rows:
		product = row.get("product")
		stock_uom_name = product_uoms.get(product)
		row_uom = stock_uom_name or display_uom

		if stock_uom_name and display_is_kg_ton and (
			stock_uom.is_kg_uom(stock_uom_name) or stock_uom.is_ton_uom(stock_uom_name)
		):
			row_uom = display_uom
			factor = stock_uom.conversion_factor(stock_uom_name, row_uom)
			if factor and factor != 1:
				row["available_qty"] = flt(row.get("available_qty")) * factor
				row["reserved_qty"] = flt(row.get("reserved_qty")) * factor
				row["issued_qty"] = flt(row.get("issued_qty")) * factor

		row["uom"] = row_uom

	return columns, rows, None, None
