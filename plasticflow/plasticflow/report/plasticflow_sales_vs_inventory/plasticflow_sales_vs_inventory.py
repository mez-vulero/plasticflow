from __future__ import annotations

from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import getdate, nowdate


def _get_date_bounds():
	invoice_bounds = frappe.db.sql(
		"""
		select min(invoice_date) as min_date, max(invoice_date) as max_date
		from `tabInvoice`
		where docstatus = 1
		""",
		as_dict=True,
	)
	stock_bounds = frappe.db.sql(
		"""
		select min(date(coalesce(last_movement, creation))) as min_date,
		       max(date(coalesce(last_movement, creation))) as max_date
		from `tabStock Ledger Entry`
		""",
		as_dict=True,
	)

	invoice_min = getdate(invoice_bounds[0].min_date) if invoice_bounds and invoice_bounds[0].min_date else None
	invoice_max = getdate(invoice_bounds[0].max_date) if invoice_bounds and invoice_bounds[0].max_date else None
	stock_min = getdate(stock_bounds[0].min_date) if stock_bounds and stock_bounds[0].min_date else None
	stock_max = getdate(stock_bounds[0].max_date) if stock_bounds and stock_bounds[0].max_date else None

	min_candidates = [d for d in (invoice_min, stock_min) if d]
	max_candidates = [d for d in (invoice_max, stock_max) if d]

	min_date = min(min_candidates) if min_candidates else None
	max_date = max(max_candidates) if max_candidates else None

	return min_date, max_date


def execute(filters=None):
	filters = filters or {}
	start_date = getdate(filters.get("from_date")) if filters.get("from_date") else None
	end_date = getdate(filters.get("to_date")) if filters.get("to_date") else None

	if not start_date or not end_date:
		min_date, max_date = _get_date_bounds()
		if not start_date:
			start_date = min_date or end_date
		if not end_date:
			end_date = max_date or start_date

	if not start_date or not end_date:
		start_date = end_date = getdate(nowdate())

	if start_date > end_date:
		start_date, end_date = end_date, start_date

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
