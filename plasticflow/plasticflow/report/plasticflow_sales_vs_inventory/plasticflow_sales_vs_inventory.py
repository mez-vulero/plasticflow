from __future__ import annotations

from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import add_days, getdate, nowdate


def execute(filters=None):
	end_date = getdate(filters.get("to_date")) if filters and filters.get("to_date") else getdate(nowdate())
	start_date = getdate(filters.get("from_date")) if filters and filters.get("from_date") else add_days(end_date, -29)

	invoice_rows = frappe.db.sql(
		"""
		select invoice_date, sum(total_amount) as total_amount
		from `tabInvoice`
		where docstatus = 1
			and invoice_date between %(start_date)s and %(end_date)s
		group by invoice_date
		""",
		{"start_date": start_date, "end_date": end_date},
		as_dict=True,
	)
	invoice_map = {getdate(row.invoice_date): float(row.total_amount or 0) for row in invoice_rows}

	stock_rows = frappe.db.sql(
		"""
		select date(coalesce(last_movement, creation)) as movement_date,
		       sum(available_qty) as available_qty
		from `tabStock Ledger Entry`
		where coalesce(last_movement, creation) between %(start_date)s and %(end_date)s
		group by date(coalesce(last_movement, creation))
		order by movement_date
		""",
		{"start_date": start_date, "end_date": end_date},
		as_dict=True,
	)
	stock_map = {getdate(row.movement_date): float(row.available_qty or 0) for row in stock_rows}

	current_total_stock = frappe.db.sql(
		"select sum(available_qty) from `tabStock Ledger Entry`"
	)[0][0] or 0

	data = []
	days = int((end_date - start_date).days)
	last_stock_snapshot = stock_map.get(start_date) or float(current_total_stock)

	for offset in range(days + 1):
		day = start_date + timedelta(days=offset)
		if day in stock_map:
			last_stock_snapshot = stock_map[day]

		data.append(
			{
				"date": day,
				"revenue": invoice_map.get(day, 0.0),
				"available_stock": float(last_stock_snapshot or 0),
			}
		)

	columns = [
		{"label": _("Date"), "fieldname": "date", "fieldtype": "Date", "width": 140},
		{"label": _("Revenue"), "fieldname": "revenue", "fieldtype": "Currency", "width": 160},
		{"label": _("Available Stock"), "fieldname": "available_stock", "fieldtype": "Float", "width": 160},
	]

	chart = {
		"data": {
			"labels": [row["date"] for row in data],
			"datasets": [
				{"name": _("Revenue"), "values": [row["revenue"] for row in data]},
				{"name": _("Available Stock"), "values": [row["available_stock"] for row in data]},
			],
		},
		"type": "line",
	}

	return columns, data, None, chart
