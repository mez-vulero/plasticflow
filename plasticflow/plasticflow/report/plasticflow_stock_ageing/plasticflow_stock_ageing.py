from __future__ import annotations

import datetime

import frappe
from frappe import _
from frappe.utils import get_datetime


BUCKETS = [
	("0-7 days", 0, 7),
	("8-30 days", 8, 30),
	("31-90 days", 31, 90),
	("90+ days", 91, None),
]


def execute(filters=None):
	filters = filters or {}
	product = filters.get("product")
	location_type = filters.get("location_type")
	warehouse = filters.get("warehouse")
	bucket_filter = filters.get("bucket")

	conditions = ["last_movement is not null"]
	params = {}
	if product:
		conditions.append("product = %(product)s")
		params["product"] = product
	if location_type:
		conditions.append("location_type = %(location_type)s")
		params["location_type"] = location_type
	if warehouse:
		conditions.append("warehouse = %(warehouse)s")
		params["warehouse"] = warehouse

	where_clause = f" where {' and '.join(conditions)}" if conditions else ""

	rows = frappe.db.sql(
		f"""
		select product,
		       location_type,
		       available_qty,
		       coalesce(landed_cost_rate, 0) as landed_cost_rate,
		       last_movement
		from `tabPlasticflow Stock Ledger Entry`
		{where_clause}
		""",
		params,
		as_dict=True,
	)

	now = get_datetime()
	aggregated = []
	for row in rows:
		if not row.last_movement:
			continue
		last = get_datetime(row.last_movement)
		days = (now - last).days if isinstance(now, datetime.datetime) else 0
		bucket = _bucket_for_days(days)
		if not bucket:
			continue
		aggregated.append(
			{
				"bucket": bucket,
				"location_type": row.location_type or "Customs",
				"quantity": float(row.available_qty or 0),
				"value": float((row.available_qty or 0) * (row.landed_cost_rate or 0)),
			}
		)

	if bucket_filter:
		aggregated = [row for row in aggregated if row["bucket"] == bucket_filter]

	by_bucket = {}
	for row in aggregated:
		key = (row["bucket"], row["location_type"])
		if key not in by_bucket:
			by_bucket[key] = {"bucket": row["bucket"], "location_type": row["location_type"], "quantity": 0.0, "value": 0.0}
		by_bucket[key]["quantity"] += row["quantity"]
		by_bucket[key]["value"] += row["value"]

	data = list(by_bucket.values())
	data.sort(key=lambda r: (BUCKET_ORDER.get(r["bucket"], 99), r["location_type"]))

	columns = [
		{"label": _("Age Bucket"), "fieldname": "bucket", "fieldtype": "Data", "width": 140},
		{"label": _("Location"), "fieldname": "location_type", "fieldtype": "Data", "width": 120},
		{"label": _("Available Qty"), "fieldname": "quantity", "fieldtype": "Float", "width": 140},
		{"label": _("Value"), "fieldname": "value", "fieldtype": "Currency", "width": 140},
	]

	chart = None
	if data:
		labels = []
		values = []
		for bucket, lower, upper in BUCKETS:
			labels.append(bucket)
			total_value = sum(row["value"] for row in data if row["bucket"] == bucket)
			values.append(total_value)
		chart = {
			"data": {"labels": labels, "datasets": [{"name": _("Value"), "values": values}]},
			"type": "bar",
		}

	return columns, data, None, chart


def _bucket_for_days(days: int) -> str | None:
	for label, lower, upper in BUCKETS:
		if upper is None and days >= lower:
			return label
		if lower <= days <= upper:
			return label
	return None


BUCKET_ORDER = {label: index for index, (label, _, _) in enumerate(BUCKETS)}
