from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import get_first_day, get_last_day, nowdate


def execute(filters=None):
	columns = [
		{"label": _("Metric"), "fieldname": "metric", "fieldtype": "Data", "width": 220},
		{"label": _("Value"), "fieldname": "value", "fieldtype": "Data", "width": 140},
		{"label": _("Context"), "fieldname": "description", "fieldtype": "Data", "width": 320},
	]

	data_points = _collect_kpis()

	data = [
		{
			"metric": _("Available Stock (MT)"),
			"value": f"{data_points['available_stock']:.2f}",
			"description": _("Total on-hand quantity across all batches."),
		},
		{
			"metric": _("Reserved Stock (MT)"),
			"value": f"{data_points['reserved_stock']:.2f}",
			"description": _("Quantity reserved against confirmed sales orders."),
		},
		{
			"metric": _("Outstanding Invoices"),
			"value": frappe.utils.fmt_money(data_points["outstanding_invoices"]),
			"description": _("Total value of submitted invoices awaiting payment."),
		},
		{
			"metric": _("Deliveries In Transit"),
			"value": str(data_points["deliveries_in_transit"]),
			"description": _("Delivery Notes submitted but not yet marked delivered."),
		},
		{
			"metric": _("Sales Booked This Month"),
			"value": frappe.utils.fmt_money(data_points["sales_total_month"]),
			"description": _("Total value of submitted sales orders this month."),
		},
		{
			"metric": _("Clearance Pending"),
			"value": str(data_points["pending_clearance"]),
			"description": _("Shipments at customs not yet cleared."),
		},
	]

	chart = {
		"data": {
			"labels": [
				_("Stock On Hand"),
				_("Reserved"),
				_("Outstanding Invoices"),
				_("Deliveries In Transit"),
			],
			"datasets": [
				{
					"name": _("Operational Snapshot"),
					"values": [
						round(data_points["available_stock"], 2),
						round(data_points["reserved_stock"], 2),
						round(data_points["outstanding_invoices"], 2),
						data_points["deliveries_in_transit"],
					],
				}
			],
		},
		"type": "bar",
		"colors": ["#1f77b4"],
	}

	return columns, data, None, chart


def _collect_kpis():
	stock_totals = frappe.db.get_all(
		"Stock Ledger Entry",
		fields=[
			"coalesce(sum(available_qty),0) as available",
			"coalesce(sum(reserved_qty),0) as reserved",
		],
	)
	available_stock = stock_totals[0].available if stock_totals else 0
	reserved_stock = stock_totals[0].reserved if stock_totals else 0

	outstanding_row = frappe.db.get_all(
		"Invoice",
		filters={"docstatus": 1},
		fields=["coalesce(sum(outstanding_amount),0) as outstanding"],
	)
	outstanding_invoices = outstanding_row[0].outstanding if outstanding_row else 0

	deliveries_in_transit = frappe.db.count(
		"Delivery Note", filters={"docstatus": 1, "status": "In Transit"}
	)

	month_start = get_first_day(nowdate())
	month_end = get_last_day(nowdate())

	sales_row = frappe.db.get_all(
		"Sales Order",
		filters={"docstatus": 1, "order_date": ["between", [month_start, month_end]]},
		fields=["coalesce(sum(total_amount),0) as total"],
	)
	sales_total_month = sales_row[0].total if sales_row else 0

	pending_clearance = frappe.db.count(
		"Import Shipment",
		{
			"docstatus": ["!=", 2],
			"clearance_status": ["in", ["In Transit", "Received", "Under Clearance", "On Hold"]],
		},
	)

	return {
		"available_stock": available_stock or 0,
		"reserved_stock": reserved_stock or 0,
		"outstanding_invoices": outstanding_invoices or 0,
		"deliveries_in_transit": deliveries_in_transit or 0,
		"sales_total_month": sales_total_month or 0,
		"pending_clearance": pending_clearance or 0,
	}
