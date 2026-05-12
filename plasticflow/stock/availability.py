"""Canonical stock-availability reader.

Single source of truth for "what stock is on hand?" across the app. Every
consumer (Sales Order FIFO walker, Sales Order ledger sanity check, Stock
Adjustment / Reconciliation reads, Stock Balance report current-snapshot,
the get_current_stock helper) reads through this module so the answer is
identical everywhere.

The truth lives in `Stock Entry Items`. `Stock Ledger Entry` is treated as
a derived cache only.
"""

from __future__ import annotations

import frappe
from frappe.utils import flt

QTY_TOLERANCE = 0.0001

WAREHOUSE_STATUSES: tuple[str, ...] = (
	"Available",
	"Reserved",
	"Partially Issued",
	"Depleted",
)
CUSTOMS_STATUSES: tuple[str, ...] = ("At Customs",)


def _status_set(location_type: str) -> tuple[str, ...]:
	if location_type == "Customs":
		return CUSTOMS_STATUSES
	return WAREHOUSE_STATUSES


def get_available_batches(
	product: str,
	*,
	location_type: str = "Warehouse",
	warehouse: str | None = None,
	import_shipment: str | None = None,
	import_shipments: list[str] | None = None,
	exclude_import_shipment: str | None = None,
	fifo: bool = True,
	for_release: bool = False,
	include_zero: bool = False,
) -> list:
	"""Return per-batch availability rows for a product at a location.

	Reads `Stock Entry Items` joined to `Stock Entries` and (left-join) the
	originating `Import Shipment Item`. This is the canonical query — every
	read site in the app must go through here so the status filter and the
	available-quantity formula are identical for everyone.

	for_release=True surfaces batches that hold reserved_qty > 0 (used when
	releasing a reservation). Otherwise the rows returned have available
	stock to consume.
	"""
	if not product:
		return []
	if not frappe.db.table_exists("Stock Entries") or not frappe.db.table_exists(
		"Stock Entry Items"
	):
		return []

	conditions: list[str] = ["se.docstatus = 1", "sei.product = %s"]
	values: list = [product]

	statuses = _status_set(location_type)
	placeholders = ", ".join(["%s"] * len(statuses))
	conditions.append(f"se.status in ({placeholders})")
	values.extend(statuses)

	if location_type == "Warehouse" and warehouse:
		conditions.append("se.warehouse = %s")
		values.append(warehouse)

	if import_shipments:
		ph = ", ".join(["%s"] * len(import_shipments))
		conditions.append(f"se.import_shipment in ({ph})")
		values.extend(import_shipments)
	elif import_shipment:
		conditions.append("se.import_shipment = %s")
		values.append(import_shipment)
	elif exclude_import_shipment:
		conditions.append("se.import_shipment != %s")
		values.append(exclude_import_shipment)

	if not include_zero:
		if for_release:
			conditions.append("coalesce(sei.reserved_qty, 0) > 0")
		else:
			conditions.append(
				"(coalesce(sei.received_qty, 0) - coalesce(sei.reserved_qty, 0) "
				"- coalesce(sei.issued_qty, 0)) > 0"
			)

	order_clause = "arrival_marker, se.creation" if fifo else "se.creation desc"

	query = f"""
		select
			sei.name as child_name,
			se.name as batch_name,
			se.import_shipment as import_shipment,
			sei.import_shipment_item as import_shipment_item,
			sei.uom as uom,
			se.status as status,
			se.warehouse as warehouse,
			coalesce(se.arrival_date, se.creation) as arrival_marker,
			se.creation as creation,
			coalesce(sei.received_qty, 0) as received_qty,
			coalesce(sei.reserved_qty, 0) as reserved_qty,
			coalesce(sei.issued_qty, 0) as issued_qty,
			(coalesce(sei.received_qty, 0) - coalesce(sei.reserved_qty, 0)
				- coalesce(sei.issued_qty, 0)) as available_qty,
			isi.quantity as original_qty,
			isi.uom as original_uom
		from `tabStock Entry Items` sei
		inner join `tabStock Entries` se on se.name = sei.parent
		left join `tabImport Shipment Item` isi on isi.name = sei.import_shipment_item
		where {" and ".join(conditions)}
		order by {order_clause}
	"""
	return frappe.db.sql(query, tuple(values), as_dict=True)


def get_available_quantity(
	product: str,
	*,
	location_type: str = "Warehouse",
	warehouse: str | None = None,
	import_shipment: str | None = None,
) -> float:
	"""Aggregate available qty for a product at a location.

	Sums the canonical per-batch view, so this number always agrees with
	what the FIFO walker can actually reserve.
	"""
	rows = get_available_batches(
		product,
		location_type=location_type,
		warehouse=warehouse,
		import_shipment=import_shipment,
	)
	return flt(sum(flt(r.available_qty) for r in rows))


def get_available_quantity_by_shipment(
	product: str,
	*,
	location_type: str,
	import_shipment: str | None,
	warehouse: str | None = None,
) -> float:
	"""Compatibility shim for callers that filtered by shipment via the ledger."""
	return get_available_quantity(
		product,
		location_type=location_type,
		warehouse=warehouse,
		import_shipment=import_shipment,
	)


def get_product_balances(
	*,
	import_shipment: str | None = None,
	warehouse: str | None = None,
) -> list:
	"""Return per-product balances across all in-status batches.

	One row per product, summing every batch the canonical reader would
	return. Used by the Stock Balance report's current-snapshot path so
	the report agrees with the FIFO walker and the reconciliation tool.

	When `warehouse` is set, customs-status entries are excluded — matching
	the historical report behaviour where the rollup row carries the
	warehouse field and customs rows have no warehouse.
	"""
	if not frappe.db.table_exists("Stock Entries") or not frappe.db.table_exists(
		"Stock Entry Items"
	):
		return []

	if warehouse:
		statuses: tuple[str, ...] = WAREHOUSE_STATUSES
	else:
		statuses = WAREHOUSE_STATUSES + CUSTOMS_STATUSES

	conditions: list[str] = ["se.docstatus = 1"]
	values: list = []

	placeholders = ", ".join(["%s"] * len(statuses))
	conditions.append(f"se.status in ({placeholders})")
	values.extend(statuses)

	if import_shipment:
		conditions.append("se.import_shipment = %s")
		values.append(import_shipment)
	if warehouse:
		conditions.append("se.warehouse = %s")
		values.append(warehouse)

	query = f"""
		select
			sei.product as product,
			coalesce(sum(coalesce(sei.received_qty, 0)
				- coalesce(sei.reserved_qty, 0)
				- coalesce(sei.issued_qty, 0)), 0) as available_qty,
			coalesce(sum(coalesce(sei.reserved_qty, 0)), 0) as reserved_qty,
			coalesce(sum(coalesce(sei.issued_qty, 0)), 0) as issued_qty,
			max(coalesce(se.modified, se.creation)) as last_movement
		from `tabStock Entry Items` sei
		inner join `tabStock Entries` se on se.name = sei.parent
		where {" and ".join(conditions)}
		group by sei.product
		order by sei.product
	"""
	return frappe.db.sql(query, tuple(values), as_dict=True)
