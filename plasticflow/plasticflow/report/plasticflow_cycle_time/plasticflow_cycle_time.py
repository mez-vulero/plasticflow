from __future__ import annotations

import frappe
from frappe import _


def execute(filters=None):
	filters = filters or {}
	from_date = filters.get("from_date")
	to_date = filters.get("to_date")
	params = {}

	clearance_conditions = [
		"clearance_status in ('Cleared', 'At Warehouse')",
		"arrival_date is not null",
		"cleared_on is not null",
	]
	if from_date:
		clearance_conditions.append("arrival_date >= %(from_date)s")
		params["from_date"] = from_date
	if to_date:
		clearance_conditions.append("arrival_date <= %(to_date)s")
		params["to_date"] = to_date

	clearance_days = frappe.db.sql(
		f"""
		select avg(datediff(cleared_on, arrival_date))
		from `tabImport Shipment`
		where {" and ".join(clearance_conditions)}
		""",
		params,
	)[0][0]

	transfer_conditions = [
		"se.docstatus = 1",
		"ce.cleared_on is not null",
	]
	if from_date:
		transfer_conditions.append("date(se.creation) >= %(from_date)s")
	if to_date:
		transfer_conditions.append("date(se.creation) <= %(to_date)s")

	transfer_days = frappe.db.sql(
		f"""
		select avg(datediff(date(se.creation), ce.cleared_on))
		from `tabStock Entries` se
		inner join `tabImport Shipment` ce on se.import_shipment = ce.name
		where {" and ".join(transfer_conditions)}
		""",
		params,
	)[0][0]

	fulfillment_conditions = ["so.order_date is not null"]
	if from_date:
		fulfillment_conditions.append("so.order_date >= %(from_date)s")
	if to_date:
		fulfillment_conditions.append("so.order_date <= %(to_date)s")

	fulfillment_days = frappe.db.sql(
		f"""
		select avg(datediff(coalesce(gp.generated_on, gp.modified), so.order_date))
		from `tabGate Pass` gp
		inner join `tabSales Order` so on gp.sales_order = so.name
		where {" and ".join(fulfillment_conditions)}
		""",
		params,
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
