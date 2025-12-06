from __future__ import annotations

import frappe
from frappe.utils import flt


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
