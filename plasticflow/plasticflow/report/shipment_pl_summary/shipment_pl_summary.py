from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt


WITHHOLDING_TAX_TYPE = "Withholding Tax 3%"
DEFAULT_PROFIT_TAX_PERCENT = 30.0


def execute(filters=None):
	filters = filters or {}
	columns = _get_columns()
	data = _get_data(filters)
	chart = _build_chart(data) if data else None
	return columns, data, None, chart


def _get_columns():
	currency = frappe.db.get_default("currency") or "ETB"
	return [
		{
			"label": _("Import Shipment"),
			"fieldname": "import_shipment",
			"fieldtype": "Link",
			"options": "Import Shipment",
			"width": 160,
		},
		{"label": _("Arrival Date"), "fieldname": "arrival_date", "fieldtype": "Date", "width": 110},
		{
			"label": _("Total Landed Cost"),
			"fieldname": "landed_cost_total",
			"fieldtype": "Currency",
			"options": currency,
			"width": 150,
		},
		{
			"label": _("Total Sales"),
			"fieldname": "total_sales",
			"fieldtype": "Currency",
			"options": currency,
			"width": 140,
		},
		{
			"label": _("Total Profit"),
			"fieldname": "total_profit",
			"fieldtype": "Currency",
			"options": currency,
			"width": 140,
		},
		{
			"label": _("Total Outstanding"),
			"fieldname": "total_outstanding",
			"fieldtype": "Currency",
			"options": currency,
			"width": 150,
		},
		{
			"label": _("Withholding Paid"),
			"fieldname": "withholding_paid",
			"fieldtype": "Currency",
			"options": currency,
			"width": 150,
		},
		{
			"label": _("Profit Tax %"),
			"fieldname": "profit_tax_percent",
			"fieldtype": "Percent",
			"width": 100,
		},
		{
			"label": _("Profit Tax"),
			"fieldname": "profit_tax",
			"fieldtype": "Currency",
			"options": currency,
			"width": 130,
		},
		{
			"label": _("Net Tax"),
			"fieldname": "net_tax",
			"fieldtype": "Currency",
			"options": currency,
			"width": 130,
		},
		{
			"label": _("Net Profit After Taxes"),
			"fieldname": "net_profit_after_taxes",
			"fieldtype": "Currency",
			"options": currency,
			"width": 170,
		},
	]


def _get_data(filters):
	conditions = ["ish.docstatus = 1"]
	params = {}

	if filters.get("import_shipment"):
		conditions.append("ish.name = %(import_shipment)s")
		params["import_shipment"] = filters["import_shipment"]
	if filters.get("from_date"):
		conditions.append("ish.shipment_date >= %(from_date)s")
		params["from_date"] = filters["from_date"]
	if filters.get("to_date"):
		conditions.append("ish.shipment_date <= %(to_date)s")
		params["to_date"] = filters["to_date"]

	where_clause = " and ".join(conditions)

	shipments = frappe.db.sql(
		f"""
		select
			ish.name as import_shipment,
			ish.arrival_date,
			coalesce(ish.total_landed_cost_local, 0) as landed_cost_total
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

	sales_rows = frappe.db.sql(
		f"""
		select
			so.import_shipment,
			coalesce(sum(so.total_net_amount), 0) as total_sales,
			coalesce(sum(so.profit_before_tax), 0) as total_profit,
			coalesce(sum(so.outstanding_amount), 0) as total_outstanding
		from `tabSales Order` so
		where so.docstatus = 1
			and so.status != 'Cancelled'
			and so.import_shipment in ({placeholders})
		group by so.import_shipment
		""",
		tuple(shipment_names),
		as_dict=True,
	)
	sales_map = {r.import_shipment: r for r in sales_rows}

	withholding_rows = frappe.db.sql(
		f"""
		select
			lcw.import_shipment,
			coalesce(sum(lct.converted_amount), 0) as withholding_paid
		from `tabLanding Cost Tax` lct
		inner join `tabLanding Cost Worksheet` lcw
			on lcw.name = lct.parent and lcw.docstatus = 1
		where lct.cost_type = %s
			and lcw.import_shipment in ({placeholders})
		group by lcw.import_shipment
		""",
		(WITHHOLDING_TAX_TYPE, *shipment_names),
		as_dict=True,
	)
	withholding_map = {r.import_shipment: flt(r.withholding_paid) for r in withholding_rows}

	profit_tax_rate_rows = frappe.db.sql(
		f"""
		select
			lcw.import_shipment,
			max(lcw.profit_tax_percent) as profit_tax_percent
		from `tabLanding Cost Worksheet` lcw
		where lcw.docstatus = 1
			and lcw.import_shipment in ({placeholders})
		group by lcw.import_shipment
		""",
		tuple(shipment_names),
		as_dict=True,
	)
	profit_tax_map = {
		r.import_shipment: flt(r.profit_tax_percent) for r in profit_tax_rate_rows
	}

	data = []
	for s in shipments:
		sale = sales_map.get(s.import_shipment) or {}
		total_profit = flt(sale.get("total_profit") or 0)
		withholding = withholding_map.get(s.import_shipment, 0)
		profit_tax_percent = profit_tax_map.get(s.import_shipment) or DEFAULT_PROFIT_TAX_PERCENT
		profit_tax = total_profit * profit_tax_percent / 100 if total_profit > 0 else 0
		net_tax = profit_tax - withholding
		net_profit_after_taxes = total_profit - net_tax

		data.append(
			{
				"import_shipment": s.import_shipment,
				"arrival_date": s.arrival_date,
				"landed_cost_total": flt(s.landed_cost_total),
				"total_sales": flt(sale.get("total_sales") or 0),
				"total_profit": total_profit,
				"total_outstanding": flt(sale.get("total_outstanding") or 0),
				"withholding_paid": withholding,
				"profit_tax_percent": profit_tax_percent,
				"profit_tax": profit_tax,
				"net_tax": net_tax,
				"net_profit_after_taxes": net_profit_after_taxes,
			}
		)

	return data


def _build_chart(data):
	labels = [row["import_shipment"] for row in data]
	return {
		"data": {
			"labels": labels,
			"datasets": [
				{"name": _("Landed Cost"), "values": [flt(r["landed_cost_total"]) for r in data]},
				{"name": _("Sales"), "values": [flt(r["total_sales"]) for r in data]},
				{"name": _("Profit"), "values": [flt(r["total_profit"]) for r in data]},
				{"name": _("Net Profit After Taxes"), "values": [flt(r["net_profit_after_taxes"]) for r in data]},
			],
		},
		"type": "bar",
	}
