from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = filters or {}
	data = _get_data(filters)

	if filters.get("import_shipment"):
		# Detailed view: one shipment — show sales order breakdown
		columns = _get_detail_columns()
		chart = _build_detail_chart(data) if data else None
	else:
		# Summary view: all shipments — one row per shipment
		columns = _get_summary_columns()
		chart = _build_summary_chart(data) if data else None

	return columns, data, None, chart


def _get_summary_columns():
	currency = frappe.get_default_currency()
	return [
		{"label": _("Import Shipment"), "fieldname": "import_shipment", "fieldtype": "Link", "options": "Import Shipment", "width": 150},
		{"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Data", "width": 120},
		{"label": _("Arrival Date"), "fieldname": "arrival_date", "fieldtype": "Date", "width": 100},
		{"label": _("Status"), "fieldname": "clearance_status", "fieldtype": "Data", "width": 110},
		{"label": _("Total Qty"), "fieldname": "total_qty", "fieldtype": "Float", "width": 90, "precision": 3},
		{"label": _("Landed Cost"), "fieldname": "landed_cost_total", "fieldtype": "Currency", "options": currency, "width": 130},
		{"label": _("Qty Sold"), "fieldname": "qty_sold", "fieldtype": "Float", "width": 90, "precision": 3},
		{"label": _("Gross Sales"), "fieldname": "gross_sales", "fieldtype": "Currency", "options": currency, "width": 130},
		{"label": _("Net Sales"), "fieldname": "net_sales", "fieldtype": "Currency", "options": currency, "width": 120},
		{"label": _("COGS"), "fieldname": "cogs", "fieldtype": "Currency", "options": currency, "width": 120},
		{"label": _("Profit"), "fieldname": "profit", "fieldtype": "Currency", "options": currency, "width": 120},
		{"label": _("Margin %"), "fieldname": "margin_percent", "fieldtype": "Percent", "width": 90},
		{"label": _("Orders"), "fieldname": "order_count", "fieldtype": "Int", "width": 70},
		{"label": _("Paid"), "fieldname": "total_paid", "fieldtype": "Currency", "options": currency, "width": 120},
		{"label": _("Outstanding"), "fieldname": "total_outstanding", "fieldtype": "Currency", "options": currency, "width": 120},
		{"label": _("Unsold Qty"), "fieldname": "unsold_qty", "fieldtype": "Float", "width": 100, "precision": 3},
		{"label": _("Est. Remaining Value"), "fieldname": "unsold_value", "fieldtype": "Currency", "options": currency, "width": 140},
	]


def _get_detail_columns():
	currency = frappe.get_default_currency()
	return [
		{"label": _("Import Shipment"), "fieldname": "import_shipment", "fieldtype": "Link", "options": "Import Shipment", "width": 150},
		{"label": _("Sales Order"), "fieldname": "sales_order", "fieldtype": "Link", "options": "Sales Order", "width": 140},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 130},
		{"label": _("Order Date"), "fieldname": "order_date", "fieldtype": "Date", "width": 100},
		{"label": _("Sales Type"), "fieldname": "sales_type", "fieldtype": "Data", "width": 90},
		{"label": _("SO Status"), "fieldname": "so_status", "fieldtype": "Data", "width": 110},
		{"label": _("Qty Sold"), "fieldname": "qty_sold", "fieldtype": "Float", "width": 90, "precision": 3},
		{"label": _("Gross Sales"), "fieldname": "gross_sales", "fieldtype": "Currency", "options": currency, "width": 120},
		{"label": _("Net Sales"), "fieldname": "net_sales", "fieldtype": "Currency", "options": currency, "width": 120},
		{"label": _("Landed Cost"), "fieldname": "cogs", "fieldtype": "Currency", "options": currency, "width": 120},
		{"label": _("Profit"), "fieldname": "profit", "fieldtype": "Currency", "options": currency, "width": 120},
		{"label": _("Margin %"), "fieldname": "margin_percent", "fieldtype": "Percent", "width": 90},
		{"label": _("Invoiced"), "fieldname": "invoiced_amount", "fieldtype": "Currency", "options": currency, "width": 110},
		{"label": _("Paid"), "fieldname": "total_paid", "fieldtype": "Currency", "options": currency, "width": 110},
		{"label": _("Outstanding"), "fieldname": "total_outstanding", "fieldtype": "Currency", "options": currency, "width": 120},
	]


def _get_data(filters):
	if filters.get("import_shipment"):
		return _get_detail_data(filters)
	return _get_summary_data(filters)


def _get_summary_data(filters):
	conditions = ["ish.docstatus = 1"]
	params = {}

	if filters.get("from_date"):
		conditions.append("ish.shipment_date >= %(from_date)s")
		params["from_date"] = filters["from_date"]
	if filters.get("to_date"):
		conditions.append("ish.shipment_date <= %(to_date)s")
		params["to_date"] = filters["to_date"]

	where_clause = " and ".join(conditions)

	# Shipment base data
	shipments = frappe.db.sql(
		f"""
		select
			ish.name as import_shipment,
			ish.supplier,
			ish.arrival_date,
			ish.clearance_status,
			ish.total_quantity as total_qty,
			coalesce(ish.total_landed_cost_local, 0) as landed_cost_total,
			coalesce(ish.per_unit_landed_cost_local, 0) as per_unit_landed_cost
		from `tabImport Shipment` ish
		where {where_clause}
		order by coalesce(ish.arrival_date, ish.shipment_date, ish.creation)
		""",
		params,
		as_dict=True,
	)

	if not shipments:
		return []

	shipment_names = [s.import_shipment for s in shipments]
	placeholders = ", ".join(["%s"] * len(shipment_names))

	# Sales data aggregated per shipment
	sales_data = frappe.db.sql(
		f"""
		select
			so.import_shipment,
			count(distinct so.name) as order_count,
			sum(so.total_quantity) as qty_sold,
			sum(so.total_gross_amount) as gross_sales,
			sum(so.total_net_amount) as net_sales,
			sum(so.landed_cost_total) as cogs,
			sum(so.profit_before_tax) as profit,
			sum(so.total_commission) as commission
		from `tabSales Order` so
		where so.docstatus = 1
			and so.status != 'Cancelled'
			and so.import_shipment in ({placeholders})
		group by so.import_shipment
		""",
		tuple(shipment_names),
		as_dict=True,
	)
	sales_map = {r.import_shipment: r for r in sales_data}

	# Payment data
	payment_data = frappe.db.sql(
		f"""
		select
			so.import_shipment,
			coalesce(sum(ps.amount_paid), 0) as total_paid
		from `tabPayment Slips` ps
		inner join `tabSales Order` so on so.name = ps.parent
		where so.docstatus = 1
			and so.status != 'Cancelled'
			and so.import_shipment in ({placeholders})
		group by so.import_shipment
		""",
		tuple(shipment_names),
		as_dict=True,
	)
	payment_map = {r.import_shipment: flt(r.total_paid) for r in payment_data}

	# Available stock per shipment
	stock_data = frappe.db.sql(
		f"""
		select
			se.import_shipment,
			sum(greatest(coalesce(sei.received_qty, 0) - coalesce(sei.reserved_qty, 0) - coalesce(sei.issued_qty, 0), 0)) as available_qty
		from `tabStock Entry Items` sei
		inner join `tabStock Entries` se on se.name = sei.parent and se.docstatus = 1
		where se.import_shipment in ({placeholders})
		group by se.import_shipment
		""",
		tuple(shipment_names),
		as_dict=True,
	)
	stock_map = {r.import_shipment: flt(r.available_qty) for r in stock_data}

	data = []
	for s in shipments:
		sale = sales_map.get(s.import_shipment) or {}
		net_sales = flt(sale.get("net_sales") or 0)
		profit = flt(sale.get("profit") or 0)
		qty_sold = flt(sale.get("qty_sold") or 0)
		gross_sales = flt(sale.get("gross_sales") or 0)
		cogs = flt(sale.get("cogs") or 0)
		total_paid = payment_map.get(s.import_shipment, 0)
		unsold_qty = stock_map.get(s.import_shipment, 0)

		data.append(
			{
				"import_shipment": s.import_shipment,
				"supplier": s.supplier,
				"arrival_date": s.arrival_date,
				"clearance_status": s.clearance_status,
				"total_qty": flt(s.total_qty),
				"landed_cost_total": flt(s.landed_cost_total),
				"qty_sold": qty_sold,
				"gross_sales": gross_sales,
				"net_sales": net_sales,
				"cogs": cogs,
				"profit": profit,
				"margin_percent": (profit / net_sales * 100) if net_sales else 0,
				"order_count": sale.get("order_count") or 0,
				"total_paid": total_paid,
				"total_outstanding": max(net_sales - total_paid, 0),
				"unsold_qty": unsold_qty,
				"unsold_value": unsold_qty * flt(s.per_unit_landed_cost),
			}
		)

	return data


def _get_detail_data(filters):
	conditions = ["so.docstatus = 1", "so.status != 'Cancelled'"]
	params = {}

	conditions.append("so.import_shipment = %(import_shipment)s")
	params["import_shipment"] = filters["import_shipment"]

	if filters.get("from_date"):
		conditions.append("so.order_date >= %(from_date)s")
		params["from_date"] = filters["from_date"]
	if filters.get("to_date"):
		conditions.append("so.order_date <= %(to_date)s")
		params["to_date"] = filters["to_date"]

	where_clause = " and ".join(conditions)

	orders = frappe.db.sql(
		f"""
		select
			so.import_shipment,
			so.name as sales_order,
			so.customer,
			so.order_date,
			so.sales_type,
			so.status as so_status,
			so.total_quantity as qty_sold,
			so.total_gross_amount as gross_sales,
			so.total_net_amount as net_sales,
			so.landed_cost_total as cogs,
			so.profit_before_tax as profit,
			so.margin_percent,
			so.invoiced_amount,
			so.outstanding_amount as total_outstanding
		from `tabSales Order` so
		where {where_clause}
		order by so.order_date, so.creation
		""",
		params,
		as_dict=True,
	)

	if not orders:
		return []

	order_names = [o.sales_order for o in orders]
	placeholders = ", ".join(["%s"] * len(order_names))

	payment_data = frappe.db.sql(
		f"""
		select
			ps.parent as sales_order,
			coalesce(sum(ps.amount_paid), 0) as total_paid
		from `tabPayment Slips` ps
		where ps.parent in ({placeholders})
		group by ps.parent
		""",
		tuple(order_names),
		as_dict=True,
	)
	payment_map = {r.sales_order: flt(r.total_paid) for r in payment_data}

	data = []
	for o in orders:
		total_paid = payment_map.get(o.sales_order, 0)
		data.append(
			{
				"import_shipment": o.import_shipment,
				"sales_order": o.sales_order,
				"customer": o.customer,
				"order_date": o.order_date,
				"sales_type": o.sales_type,
				"so_status": o.so_status,
				"qty_sold": flt(o.qty_sold),
				"gross_sales": flt(o.gross_sales),
				"net_sales": flt(o.net_sales),
				"cogs": flt(o.cogs),
				"profit": flt(o.profit),
				"margin_percent": flt(o.margin_percent),
				"invoiced_amount": flt(o.invoiced_amount),
				"total_paid": total_paid,
				"total_outstanding": flt(o.total_outstanding),
			}
		)

	return data


def _build_summary_chart(data):
	labels = [row["import_shipment"] for row in data]
	return {
		"data": {
			"labels": labels,
			"datasets": [
				{"name": _("Landed Cost"), "values": [flt(r["landed_cost_total"]) for r in data]},
				{"name": _("Net Sales"), "values": [flt(r["net_sales"]) for r in data]},
				{"name": _("Profit"), "values": [flt(r["profit"]) for r in data]},
			],
		},
		"type": "bar",
	}


def _build_detail_chart(data):
	labels = [row["sales_order"] for row in data]
	return {
		"data": {
			"labels": labels,
			"datasets": [
				{"name": _("Net Sales"), "values": [flt(r["net_sales"]) for r in data]},
				{"name": _("Paid"), "values": [flt(r["total_paid"]) for r in data]},
				{"name": _("Outstanding"), "values": [flt(r["total_outstanding"]) for r in data]},
			],
		},
		"type": "bar",
	}
