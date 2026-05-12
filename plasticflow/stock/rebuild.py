"""Rebuild + audit for the Stock Ledger Entry cache.

`Stock Entry Items` is the source of truth. `Stock Ledger Entry` is a
denormalised per-slot rollup used by reports. Historically, multiple write
paths (sync_shipment_customs_balances, transfer_shipment_to_warehouse,
update_warehouse_stock, apply_delta) wrote to the same shipment-keyed slot
with different formulas, so the cache could drift away from the truth.

This module provides:

* `audit()` — read-only diff between the rollup and the truth.
* `rebuild_all()` — overwrite every rollup row from the truth, idempotent,
  no Stock Ledger Movement rows emitted.

Both are safe to run on production. The rebuild is what the post-deploy
patch invokes.
"""

from __future__ import annotations

import frappe
from frappe.utils import flt

from plasticflow.stock import ledger as stock_ledger
from plasticflow.stock.availability import (
	CUSTOMS_STATUSES,
	QTY_TOLERANCE,
	WAREHOUSE_STATUSES,
)

LEDGER_DOCTYPE = "Stock Ledger Entry"


def _iter_warehouse_slots():
	"""Yield (slot_key, expected) for each warehouse Stock Entry."""
	if not frappe.db.table_exists("Stock Entries"):
		return
	placeholders = ", ".join(["%s"] * len(WAREHOUSE_STATUSES))
	rows = frappe.db.sql(
		f"""
		select
			se.name as stock_entry,
			se.warehouse as warehouse,
			se.import_shipment as import_shipment,
			sei.product as product,
			coalesce(sum(sei.received_qty), 0) as received,
			coalesce(sum(sei.reserved_qty), 0) as reserved,
			coalesce(sum(sei.issued_qty), 0) as issued
		from `tabStock Entries` se
		inner join `tabStock Entry Items` sei on sei.parent = se.name
		where se.docstatus = 1 and se.status in ({placeholders})
		group by se.name, se.warehouse, se.import_shipment, sei.product
		""",
		WAREHOUSE_STATUSES,
		as_dict=True,
	)
	for row in rows:
		available = max(flt(row.received) - flt(row.reserved) - flt(row.issued), 0)
		yield (
			{
				"product": row.product,
				"location_type": "Warehouse",
				"location_reference": row.stock_entry,
				"warehouse": row.warehouse,
				"stock_entry": row.stock_entry,
				"import_shipment": row.import_shipment,
			},
			{
				"available": available,
				"reserved": flt(row.reserved),
				"issued": flt(row.issued),
			},
		)


def _iter_customs_slots():
	"""Yield (slot_key, expected) for customs-side stock per shipment+product.

	Customs balances are keyed by shipment, not by stock entry — multiple
	customs-status entries for one shipment collapse into one rollup row.
	"""
	if not frappe.db.table_exists("Stock Entries"):
		return
	placeholders = ", ".join(["%s"] * len(CUSTOMS_STATUSES))
	rows = frappe.db.sql(
		f"""
		select
			se.import_shipment as import_shipment,
			sei.product as product,
			coalesce(sum(sei.received_qty), 0) as received,
			coalesce(sum(sei.reserved_qty), 0) as reserved,
			coalesce(sum(sei.issued_qty), 0) as issued,
			min(se.name) as stock_entry
		from `tabStock Entries` se
		inner join `tabStock Entry Items` sei on sei.parent = se.name
		where se.docstatus = 1 and se.status in ({placeholders})
			and se.import_shipment is not null and se.import_shipment != ''
		group by se.import_shipment, sei.product
		""",
		CUSTOMS_STATUSES,
		as_dict=True,
	)
	for row in rows:
		available = max(flt(row.received) - flt(row.reserved) - flt(row.issued), 0)
		yield (
			{
				"product": row.product,
				"location_type": "Customs",
				"location_reference": row.import_shipment,
				"warehouse": None,
				"stock_entry": row.stock_entry,
				"import_shipment": row.import_shipment,
			},
			{
				"available": available,
				"reserved": flt(row.reserved),
				"issued": flt(row.issued),
			},
		)


def _current_rollup(slot_key):
	filters = {
		"product": slot_key["product"],
		"location_type": slot_key["location_type"],
		"location_reference": slot_key["location_reference"],
	}
	if slot_key["warehouse"]:
		filters["warehouse"] = slot_key["warehouse"]
	if slot_key["import_shipment"]:
		filters["import_shipment"] = slot_key["import_shipment"]
	rows = frappe.db.get_all(
		LEDGER_DOCTYPE,
		filters=filters,
		fields=["coalesce(sum(available_qty), 0) as available",
				"coalesce(sum(reserved_qty), 0) as reserved",
				"coalesce(sum(issued_qty), 0) as issued"],
	)
	if not rows:
		return {"available": 0.0, "reserved": 0.0, "issued": 0.0}
	row = rows[0]
	return {
		"available": flt(row.get("available")),
		"reserved": flt(row.get("reserved")),
		"issued": flt(row.get("issued")),
	}


def _diff(actual, expected):
	return {
		"available": flt(expected["available"]) - flt(actual["available"]),
		"reserved": flt(expected["reserved"]) - flt(actual["reserved"]),
		"issued": flt(expected["issued"]) - flt(actual["issued"]),
	}


def _significant(diff):
	return (
		abs(diff["available"]) >= QTY_TOLERANCE
		or abs(diff["reserved"]) >= QTY_TOLERANCE
		or abs(diff["issued"]) >= QTY_TOLERANCE
	)


@frappe.whitelist()
def audit():
	"""Read-only diff between Stock Ledger Entry and the canonical truth.

	Returns the list of slots whose rollup disagrees with what the items
	add up to. Safe to run on production — touches no rows.
	"""
	drift = []
	for slot_key, expected in _iter_warehouse_slots():
		actual = _current_rollup(slot_key)
		diff = _diff(actual, expected)
		if _significant(diff):
			drift.append({**slot_key, "actual": actual, "expected": expected, "diff": diff})
	for slot_key, expected in _iter_customs_slots():
		actual = _current_rollup(slot_key)
		diff = _diff(actual, expected)
		if _significant(diff):
			drift.append({**slot_key, "actual": actual, "expected": expected, "diff": diff})
	return {
		"drift_count": len(drift),
		"rows": drift,
	}


def rebuild_all(*, log_progress: bool = True):
	"""Overwrite every Stock Ledger Entry row from the canonical truth.

	Idempotent. Does not emit Stock Ledger Movement rows — the historical
	audit log is preserved verbatim. Run from the post-deploy patch and at
	any time afterwards if a discrepancy is reported.
	"""
	rebuilt = 0
	for slot_key, expected in _iter_warehouse_slots():
		stock_ledger.set_balances(
			slot_key["product"],
			slot_key["location_type"],
			slot_key["location_reference"],
			available=expected["available"],
			reserved=expected["reserved"],
			issued=expected["issued"],
			warehouse=slot_key["warehouse"],
			stock_entry=slot_key["stock_entry"],
			import_shipment=slot_key["import_shipment"],
			remarks="Rebuilt from Stock Entry Items",
			skip_movement_log=True,
		)
		rebuilt += 1

	for slot_key, expected in _iter_customs_slots():
		stock_ledger.set_balances(
			slot_key["product"],
			slot_key["location_type"],
			slot_key["location_reference"],
			available=expected["available"],
			reserved=expected["reserved"],
			issued=expected["issued"],
			warehouse=None,
			stock_entry=slot_key["stock_entry"],
			import_shipment=slot_key["import_shipment"],
			remarks="Rebuilt from Stock Entry Items",
			skip_movement_log=True,
		)
		rebuilt += 1

	_zero_orphan_rollups()

	frappe.db.commit()
	if log_progress:
		frappe.logger().info(f"plasticflow.stock.rebuild: rebuilt {rebuilt} ledger slots")
	return rebuilt


def _zero_orphan_rollups():
	"""Zero out rollup rows that no longer correspond to live, in-status entries.

	A row whose `stock_entry` no longer exists, or whose parent is
	cancelled or has moved out of the canonical status set, is stale.
	We zero the balances rather than delete, so historical Stock Ledger
	Movement rows still resolve their `entry` link.
	"""
	if not frappe.db.table_exists(LEDGER_DOCTYPE):
		return
	rows = frappe.db.sql(
		f"""
		select sle.name, sle.product, sle.location_type, sle.location_reference,
			sle.warehouse, sle.stock_entry, sle.import_shipment,
			sle.available_qty, sle.reserved_qty, sle.issued_qty
		from `tab{LEDGER_DOCTYPE}` sle
		left join `tabStock Entries` se on se.name = sle.stock_entry
		where (se.name is null or se.docstatus != 1)
			and (sle.available_qty != 0 or sle.reserved_qty != 0 or sle.issued_qty != 0)
		""",
		as_dict=True,
	)
	for row in rows:
		stock_ledger.set_balances(
			row.product,
			row.location_type,
			row.location_reference,
			available=0,
			reserved=0,
			issued=0,
			warehouse=row.warehouse,
			stock_entry=row.stock_entry,
			import_shipment=row.import_shipment,
			remarks="Zeroed during rebuild — parent stock entry missing or cancelled",
			skip_movement_log=True,
		)
