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
	currency = frappe.get_default_currency()
	return [
		{"label": _("Import Shipment"), "fieldname": "import_shipment", "fieldtype": "Link", "options": "Import Shipment", "width": 160},
		{"label": _("Product"), "fieldname": "product", "fieldtype": "Link", "options": "Product", "width": 160},
		{"label": _("Quantity Sold"), "fieldname": "quantity_sold", "fieldtype": "Float", "width": 120, "precision": 3},
		{"label": _("Gross Sales (VAT Incl.)"), "fieldname": "gross_sales", "fieldtype": "Currency", "options": currency, "width": 160},
		{"label": _("Net Sales"), "fieldname": "net_sales", "fieldtype": "Currency", "options": currency, "width": 140},
		{"label": _("Withholding"), "fieldname": "withholding", "fieldtype": "Currency", "options": currency, "width": 130},
		{"label": _("Landed Cost"), "fieldname": "landed_cost", "fieldtype": "Currency", "options": currency, "width": 140},
		{"label": _("Commission"), "fieldname": "commission", "fieldtype": "Currency", "options": currency, "width": 130},
		{"label": _("Profit Before Tax"), "fieldname": "profit_before_tax", "fieldtype": "Currency", "options": currency, "width": 160},
		{"label": _("Margin %"), "fieldname": "margin_percent", "fieldtype": "Percent", "width": 110},
	]


def _get_data(filters):
	conditions, params = _build_conditions(filters)
	rows = frappe.db.sql(
		f"""
		select
			coalesce(isi.parent, so.import_shipment) as import_shipment,
			soi.product,
			coalesce(soi.product_name, soi.product) as product_name,
			sum(soi.quantity) as quantity_sold,
			sum(soi.gross_amount) as gross_sales,
			sum(soi.net_amount) as net_sales,
			sum(soi.withholding_amount) as withholding,
			sum(soi.commission_amount) as commission,
			avg(isi.landed_cost_rate_local) as landed_cost_rate_local
		from `tabSales Order Item` soi
		inner join `tabSales Order` so on so.name = soi.parent
		left join `tabImport Shipment Item` isi on isi.name = soi.import_shipment_item
		where so.docstatus = 1 {conditions}
		group by coalesce(isi.parent, so.import_shipment), soi.product
		order by coalesce(isi.parent, so.import_shipment), soi.product
		""",
		params,
		as_dict=True,
	)

	data = []
	for row in rows:
		quantity = flt(row.quantity_sold or 0)
		landed_cost_rate = flt(row.landed_cost_rate_local or 0)
		if not landed_cost_rate and row.import_shipment:
			landed_cost_rate = flt(
				frappe.db.get_value("Import Shipment", row.import_shipment, "per_unit_landed_cost_local") or 0
			)
		landed_cost_total = landed_cost_rate * quantity
		net_sales = flt(row.net_sales or 0)
		commission = flt(row.commission or 0)
		profit_before_tax = net_sales - landed_cost_total - commission
		margin_percent = (profit_before_tax / net_sales * 100) if net_sales else 0

		data.append(
			{
				"import_shipment": row.import_shipment,
				"product": row.product,
				"product_name": row.product_name,
				"quantity_sold": quantity,
				"gross_sales": flt(row.gross_sales or 0),
				"net_sales": net_sales,
				"withholding": flt(row.withholding or 0),
				"landed_cost": landed_cost_total,
				"commission": commission,
				"profit_before_tax": profit_before_tax,
				"margin_percent": margin_percent,
			}
		)

	return data


def _build_conditions(filters):
	conditions = []
	params: dict[str, object] = {}

	if filters.get("import_shipment"):
		conditions.append("and coalesce(isi.parent, so.import_shipment) = %(import_shipment)s")
		params["import_shipment"] = filters["import_shipment"]
	if filters.get("product"):
		conditions.append("and soi.product = %(product)s")
		params["product"] = filters["product"]
	if filters.get("from_date"):
		conditions.append("and so.order_date >= %(from_date)s")
		params["from_date"] = filters["from_date"]
	if filters.get("to_date"):
		conditions.append("and so.order_date <= %(to_date)s")
		params["to_date"] = filters["to_date"]

	return " ".join(conditions), params


def _build_chart(data):
	labels = [f"{row['import_shipment'] or _('Unassigned')} - {row['product']}" for row in data]
	values = [flt(row["profit_before_tax"]) for row in data]
	return {
		"data": {
			"labels": labels,
			"datasets": [
				{
					"name": _("Profit Before Tax"),
					"values": values,
				}
			],
		},
		"type": "bar",
	}
