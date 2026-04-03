from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = filters or {}
	columns = _get_columns()
	data = _get_data(filters)
	chart = _build_chart(data) if data else None
	return columns, data, None, chart


def _get_columns():
	currency = frappe.db.get_default("currency") or "ETB"
	return [
		{"label": _("Import Shipment"), "fieldname": "import_shipment", "fieldtype": "Link", "options": "Import Shipment", "width": 150},
		{"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Data", "width": 130},
		{"label": _("Shipment Date"), "fieldname": "shipment_date", "fieldtype": "Date", "width": 110},
		{"label": _("Clearance Status"), "fieldname": "clearance_status", "fieldtype": "Data", "width": 130},
		{"label": _("Product"), "fieldname": "product", "fieldtype": "Link", "options": "Product", "width": 140},
		{"label": _("Shipment Qty"), "fieldname": "shipment_qty", "fieldtype": "Float", "width": 110, "precision": 3},
		{"label": _("Received Qty"), "fieldname": "received_qty", "fieldtype": "Float", "width": 110, "precision": 3},
		{"label": _("Available Qty"), "fieldname": "available_qty", "fieldtype": "Float", "width": 110, "precision": 3},
		{"label": _("Reserved Qty"), "fieldname": "reserved_qty", "fieldtype": "Float", "width": 110, "precision": 3},
		{"label": _("Issued Qty"), "fieldname": "issued_qty", "fieldtype": "Float", "width": 100, "precision": 3},
		{"label": _("Landed Cost/Unit"), "fieldname": "landed_cost_rate", "fieldtype": "Currency", "options": currency, "width": 130},
		{"label": _("Stock Value"), "fieldname": "stock_value", "fieldtype": "Currency", "options": currency, "width": 130},
	]


def _get_data(filters):
	conditions = ["ish.docstatus = 1"]
	params = {}

	if filters.get("import_shipment"):
		conditions.append("ish.name = %(import_shipment)s")
		params["import_shipment"] = filters["import_shipment"]
	if filters.get("product"):
		conditions.append("isi.product = %(product)s")
		params["product"] = filters["product"]
	if filters.get("clearance_status"):
		conditions.append("ish.clearance_status = %(clearance_status)s")
		params["clearance_status"] = filters["clearance_status"]

	where_clause = " and ".join(conditions)

	rows = frappe.db.sql(
		f"""
		select
			ish.name as import_shipment,
			ish.supplier,
			ish.shipment_date,
			ish.clearance_status,
			isi.product,
			coalesce(isi.product_name, isi.product) as product_name,
			isi.quantity as shipment_qty,
			isi.landed_cost_rate_local,
			coalesce(sei_totals.received_qty, 0) as received_qty,
			coalesce(sei_totals.available_qty, 0) as available_qty,
			coalesce(sei_totals.reserved_qty, 0) as reserved_qty,
			coalesce(sei_totals.issued_qty, 0) as issued_qty
		from `tabImport Shipment Item` isi
		inner join `tabImport Shipment` ish on ish.name = isi.parent
		left join (
			select
				sei.import_shipment_item,
				sum(coalesce(sei.received_qty, 0)) as received_qty,
				sum(greatest(coalesce(sei.received_qty, 0) - coalesce(sei.reserved_qty, 0) - coalesce(sei.issued_qty, 0), 0)) as available_qty,
				sum(coalesce(sei.reserved_qty, 0)) as reserved_qty,
				sum(coalesce(sei.issued_qty, 0)) as issued_qty
			from `tabStock Entry Items` sei
			inner join `tabStock Entries` se on se.name = sei.parent and se.docstatus = 1
			group by sei.import_shipment_item
		) sei_totals on sei_totals.import_shipment_item = isi.name
		where {where_clause}
		order by ish.shipment_date, ish.creation, isi.idx
		""",
		params,
		as_dict=True,
	)

	data = []
	for row in rows:
		landed_cost_rate = flt(row.landed_cost_rate_local or 0)
		available = flt(row.available_qty or 0)
		data.append(
			{
				"import_shipment": row.import_shipment,
				"supplier": row.supplier,
				"shipment_date": row.shipment_date,
				"clearance_status": row.clearance_status,
				"product": row.product,
				"shipment_qty": flt(row.shipment_qty or 0),
				"received_qty": flt(row.received_qty or 0),
				"available_qty": available,
				"reserved_qty": flt(row.reserved_qty or 0),
				"issued_qty": flt(row.issued_qty or 0),
				"landed_cost_rate": landed_cost_rate,
				"stock_value": available * landed_cost_rate,
			}
		)

	return data


def _build_chart(data):
	product_totals = {}
	for row in data:
		product = row["product"]
		if product not in product_totals:
			product_totals[product] = {"available": 0, "reserved": 0, "issued": 0}
		product_totals[product]["available"] += flt(row["available_qty"])
		product_totals[product]["reserved"] += flt(row["reserved_qty"])
		product_totals[product]["issued"] += flt(row["issued_qty"])

	labels = list(product_totals.keys())
	return {
		"data": {
			"labels": labels,
			"datasets": [
				{"name": _("Available"), "values": [product_totals[p]["available"] for p in labels]},
				{"name": _("Reserved"), "values": [product_totals[p]["reserved"] for p in labels]},
				{"name": _("Issued"), "values": [product_totals[p]["issued"] for p in labels]},
			],
		},
		"type": "bar",
		"barOptions": {"stacked": True},
	}
