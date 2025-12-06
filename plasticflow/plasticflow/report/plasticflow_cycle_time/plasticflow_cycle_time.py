from __future__ import annotations

import frappe
from frappe import _


def execute(filters=None):
	clearance_days = frappe.db.sql(
		"""
		select avg(datediff(cleared_on, arrival_date))
		from `tabImport Shipment`
		where clearance_status in ('Cleared', 'At Warehouse')
			and arrival_date is not null
			and cleared_on is not null
		"""
	)[0][0]

	transfer_days = frappe.db.sql(
		"""
		select avg(datediff(date(se.creation), ce.cleared_on))
		from `tabStock Entries` se
		inner join `tabImport Shipment` ce on se.import_shipment = ce.name
		where se.docstatus = 1
			and ce.cleared_on is not null
		"""
	)[0][0]

	fulfillment_days = frappe.db.sql(
		"""
		select avg(datediff(coalesce(gpr.dispatched_on, gpr.modified), so.order_date))
		from `tabGate Pass Request` gpr
		inner join `tabSales Order` so on gpr.sales_order = so.name
		where gpr.status = 'Dispatched'
			and so.order_date is not null
		"""
	)[0][0]

	metrics = [
		{"stage": _("Customs Clearance"), "avg_days": round(float(clearance_days or 0), 1)},
		{"stage": _("Warehouse Transfer"), "avg_days": round(float(transfer_days or 0), 1)},
		{"stage": _("Fulfilment to Delivery"), "avg_days": round(float(fulfillment_days or 0), 1)},
	]

	columns = [
		{"label": _("Stage"), "fieldname": "stage", "fieldtype": "Data", "width": 220},
		{"label": _("Average Days"), "fieldname": "avg_days", "fieldtype": "Float", "width": 140},
	]

	data = metrics

	chart = {
		"data": {
			"labels": [row["stage"] for row in metrics],
			"datasets": [
				{
					"name": _("Average Days"),
					"values": [row["avg_days"] for row in metrics],
				}
			],
		},
		"type": "bar",
	}

	return columns, data, None, chart
