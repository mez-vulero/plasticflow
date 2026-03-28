from __future__ import annotations

import frappe
from frappe.utils import flt, getdate, get_first_day, get_last_day, nowdate


@frappe.whitelist()
def get_average_clearance_days(filters: dict[str, str] | None = None) -> dict[str, object]:
	"""Return the average number of days between arrival and clearance for completed shipments."""

	rows = frappe.db.sql(
		"""
		select avg(datediff(coalesce(cleared_on, current_date), arrival_date)) as avg_days
		from `tabImport Shipment`
		where clearance_status in ('Cleared', 'At Warehouse')
			and arrival_date is not null
			and cleared_on is not null
		""",
		as_dict=True,
	)

	avg_days = flt(rows[0].avg_days) if rows and rows[0].avg_days is not None else 0

	return {
		"value": round(avg_days, 1),
		"fieldtype": "Float",
		"suffix": "days",
		"route": ["List", "Import Shipment"],
	}


@frappe.whitelist()
def get_cash_collected_this_month(filters: dict[str, str] | None = None) -> dict[str, object]:
	"""Sum of verified payment slips for the current month."""
	today = getdate(nowdate())
	first_day = get_first_day(today)
	last_day = get_last_day(today)

	result = frappe.db.sql(
		"""
		select coalesce(sum(ps.amount_paid), 0) as total
		from `tabPayment Slips` ps
		where ps.parenttype = 'Sales Order'
			and ps.slip_status = 'verified'
			and ps.date_uploaded between %s and %s
		""",
		(first_day, last_day),
		as_dict=True,
	)

	total = flt(result[0].total) if result else 0

	return {
		"value": total,
		"fieldtype": "Currency",
		"route": ["List", "Sales Order"],
	}


@frappe.whitelist()
def get_collection_rate(filters: dict[str, str] | None = None) -> dict[str, object]:
	"""Percentage of invoiced amount that has been collected via verified payment slips."""
	invoiced = frappe.db.sql(
		"""
		select coalesce(sum(total_amount), 0) as total
		from `tabInvoice`
		where docstatus = 1
		""",
		as_dict=True,
	)

	collected = frappe.db.sql(
		"""
		select coalesce(sum(ps.amount_paid), 0) as total
		from `tabPayment Slips` ps
		where ps.parenttype = 'Sales Order'
			and ps.slip_status = 'verified'
		""",
		as_dict=True,
	)

	total_invoiced = flt(invoiced[0].total) if invoiced else 0
	total_collected = flt(collected[0].total) if collected else 0

	rate = (total_collected / total_invoiced * 100) if total_invoiced > 0 else 0

	return {
		"value": round(rate, 1),
		"fieldtype": "Percent",
		"route": ["List", "Invoice"],
	}


@frappe.whitelist()
def get_average_landed_cost(filters: dict[str, str] | None = None) -> dict[str, object]:
	"""Average per-unit landed cost across all costed shipments."""
	result = frappe.db.sql(
		"""
		select avg(per_unit_landed_cost_local) as avg_cost
		from `tabImport Shipment`
		where docstatus = 1
			and per_unit_landed_cost_local > 0
		""",
		as_dict=True,
	)

	avg_cost = flt(result[0].avg_cost) if result and result[0].avg_cost is not None else 0

	return {
		"value": round(avg_cost, 2),
		"fieldtype": "Currency",
		"route": ["List", "Import Shipment"],
	}


@frappe.whitelist()
def get_average_profit_margin(filters: dict[str, str] | None = None) -> dict[str, object]:
	"""Average profit margin percentage across submitted sales orders."""
	result = frappe.db.sql(
		"""
		select avg(margin_percent) as avg_margin
		from `tabSales Order`
		where docstatus = 1
			and margin_percent is not null
			and margin_percent != 0
		""",
		as_dict=True,
	)

	avg_margin = flt(result[0].avg_margin) if result and result[0].avg_margin is not None else 0

	return {
		"value": round(avg_margin, 1),
		"fieldtype": "Percent",
		"route": ["List", "Sales Order"],
	}
