import frappe
from frappe.utils import flt, now_datetime

LEDGER_DOCTYPE = "Plasticflow Stock Ledger Entry"


def _get_filters(product, location_type, location_reference, warehouse=None, customs_entry=None, plasticflow_stock_entry=None):
	filters = {
		"product": product,
		"location_type": location_type,
		"location_reference": location_reference,
	}
	if warehouse:
		filters["warehouse"] = warehouse
	if customs_entry:
		filters["customs_entry"] = customs_entry
	if plasticflow_stock_entry:
		filters["plasticflow_stock_entry"] = plasticflow_stock_entry
	return filters


def _get_or_create(product, location_type, location_reference, warehouse=None, customs_entry=None, plasticflow_stock_entry=None):
	base_filters = _get_filters(product, location_type, location_reference, warehouse, customs_entry, None)
	base_filters.pop("plasticflow_stock_entry", None)

	existing = frappe.db.get_all(
		LEDGER_DOCTYPE,
		filters=base_filters,
		fields=["name", "last_movement", "creation"],
	)

	doc = None
	if existing:
		existing.sort(key=lambda row: row.last_movement or row.creation, reverse=True)
		doc = frappe.get_doc(LEDGER_DOCTYPE, existing[0].name)
		for duplicate in existing[1:]:
			frappe.delete_doc(
				LEDGER_DOCTYPE,
				duplicate.name,
				ignore_permissions=True,
				force=1,
				delete_permanently=True,
			)

	if not doc:
		doc = frappe.new_doc(LEDGER_DOCTYPE)

	doc.product = product
	doc.location_type = location_type
	doc.location_reference = location_reference
	doc.warehouse = warehouse
	doc.customs_entry = customs_entry
	doc.plasticflow_stock_entry = plasticflow_stock_entry

	return doc


def set_balances(
	product,
	location_type,
	location_reference,
	*,
	available=None,
	reserved=None,
	issued=None,
	warehouse=None,
	customs_entry=None,
	plasticflow_stock_entry=None,
	remarks=None,
):
	"""Set absolute balances for a ledger slot."""
	doc = _get_or_create(product, location_type, location_reference, warehouse, customs_entry, plasticflow_stock_entry)
	if available is not None:
		doc.available_qty = available
	if reserved is not None:
		doc.reserved_qty = reserved
	if issued is not None:
		doc.issued_qty = issued
	if remarks is not None:
		doc.remarks = remarks
	doc.last_movement = now_datetime()
	if doc.is_new():
		doc.insert(ignore_permissions=True)
	else:
		doc.save(ignore_permissions=True)
	return doc


def apply_delta(
	product,
	location_type,
	location_reference,
	*,
	available_delta=0.0,
	reserved_delta=0.0,
	issued_delta=0.0,
	warehouse=None,
	customs_entry=None,
	plasticflow_stock_entry=None,
	remarks=None,
):
	"""Adjust balances by delta values."""
	doc = _get_or_create(product, location_type, location_reference, warehouse, customs_entry, plasticflow_stock_entry)
	doc.available_qty = max((doc.available_qty or 0) + available_delta, 0)
	doc.reserved_qty = max((doc.reserved_qty or 0) + reserved_delta, 0)
	doc.issued_qty = max((doc.issued_qty or 0) + issued_delta, 0)
	if remarks is not None:
		doc.remarks = remarks
	doc.last_movement = now_datetime()
	if doc.is_new():
		doc.insert(ignore_permissions=True)
	else:
		doc.save(ignore_permissions=True)
	return doc


def clear_slot(product, location_type, location_reference, warehouse=None, customs_entry=None, plasticflow_stock_entry=None):
	base_filters = _get_filters(product, location_type, location_reference, warehouse, customs_entry, None)
	base_filters.pop("plasticflow_stock_entry", None)
	names = frappe.db.get_all(
		LEDGER_DOCTYPE,
		filters=base_filters,
		pluck="name",
	)
	for name in names:
		frappe.delete_doc(LEDGER_DOCTYPE, name, ignore_permissions=True, force=1, delete_permanently=True)


# Convenience helpers -----------------------------------------------------

def get_available_quantity(product, *, location_type, warehouse=None):
	"""Return aggregated available quantity for a product at a location type."""
	filters = {
		"product": product,
		"location_type": location_type,
	}
	if warehouse:
		filters["warehouse"] = warehouse
	rows = frappe.db.get_all(
		LEDGER_DOCTYPE,
		filters=filters,
		fields=["coalesce(sum(available_qty), 0) as available"],
	)
	return flt(rows[0].available) if rows else 0.0


def _get_transferred_totals_by_customs_item(customs_entry_name):
	rows = frappe.db.sql(
		"""
		select
			sei.customs_entry_item as customs_entry_item,
			coalesce(sum(sei.received_qty), 0) as total_transferred
		from `tabPlasticflow Stock Entry Item` sei
		inner join `tabPlasticflow Stock Entry` se on se.name = sei.parent
		where se.docstatus = 1
			and se.customs_entry = %s
			and se.status != 'At Customs'
		group by sei.customs_entry_item
		""",
		(customs_entry_name,),
		as_dict=True,
	)
	return {row.customs_entry_item: row.total_transferred for row in rows}

def sync_customs_entry(customs_entry_doc, *, plasticflow_stock_entry=None):
	linked_entry = plasticflow_stock_entry or customs_entry_doc.get("plasticflow_stock_entry")
	for item in customs_entry_doc.items:
		set_balances(
			item.product,
			"Customs",
			customs_entry_doc.name,
			available=item.quantity or 0,
			warehouse=None,
			customs_entry=customs_entry_doc.name,
			plasticflow_stock_entry=linked_entry,
			remarks="Customs stock awaiting transfer",
		)


def clear_customs_entry(customs_entry_doc):
	for item in customs_entry_doc.items:
		clear_slot(
			item.product,
			"Customs",
			customs_entry_doc.name,
			warehouse=None,
			customs_entry=customs_entry_doc.name,
			plasticflow_stock_entry=customs_entry_doc.plasticflow_stock_entry,
		)


def add_warehouse_stock(plasticflow_stock_entry_doc):
	for item in plasticflow_stock_entry_doc.items:
		set_balances(
			item.product,
			"Warehouse",
			plasticflow_stock_entry_doc.name,
			available=item.available_qty or item.received_qty or 0,
			warehouse=plasticflow_stock_entry_doc.warehouse,
			customs_entry=plasticflow_stock_entry_doc.customs_entry,
			plasticflow_stock_entry=plasticflow_stock_entry_doc.name,
			remarks="Stock available in warehouse",
		)


def update_warehouse_stock(plasticflow_stock_entry_doc):
	for item in plasticflow_stock_entry_doc.items:
		set_balances(
			item.product,
			"Warehouse",
			plasticflow_stock_entry_doc.name,
			available=item.available_qty or item.received_qty or 0,
			reserved=item.reserved_qty or 0,
			issued=item.issued_qty or 0,
			warehouse=plasticflow_stock_entry_doc.warehouse,
			customs_entry=plasticflow_stock_entry_doc.customs_entry,
			plasticflow_stock_entry=plasticflow_stock_entry_doc.name,
			remarks="Stock available in warehouse",
		)


def transfer_customs_to_warehouse(customs_entry_doc, plasticflow_stock_entry_doc):
	customs_item_map = {child.name: (child.quantity or 0) for child in customs_entry_doc.items}
	transferred_totals = _get_transferred_totals_by_customs_item(customs_entry_doc.name)

	for item in plasticflow_stock_entry_doc.items:
		qty = item.available_qty or item.received_qty or 0
		if not qty:
			continue

		customs_qty = customs_item_map.get(item.customs_entry_item)
		if customs_qty is None:
			customs_qty = item.received_qty or item.available_qty or 0
		total_transferred = transferred_totals.get(item.customs_entry_item, 0)
		remaining_at_customs = max(customs_qty - total_transferred, 0)

		# update customs balances with remaining stock and record movement in issued qty
		set_balances(
			item.product,
			"Customs",
			customs_entry_doc.name,
			available=remaining_at_customs,
			reserved=0,
			issued=total_transferred,
			warehouse=None,
			customs_entry=customs_entry_doc.name,
			plasticflow_stock_entry=plasticflow_stock_entry_doc.name,
			remarks="Transferred to warehouse",
		)

		# set warehouse balances to current entry values
		set_balances(
			item.product,
			"Warehouse",
			plasticflow_stock_entry_doc.name,
			available=item.available_qty or item.received_qty or 0,
			reserved=item.reserved_qty or 0,
			issued=item.issued_qty or 0,
			warehouse=plasticflow_stock_entry_doc.warehouse,
			customs_entry=customs_entry_doc.name,
			plasticflow_stock_entry=plasticflow_stock_entry_doc.name,
			remarks="Stock available in warehouse",
		)


def clear_stock_entry(plasticflow_stock_entry_doc):
	for item in plasticflow_stock_entry_doc.items:
		clear_slot(
			item.product,
			"Warehouse",
			plasticflow_stock_entry_doc.name,
			warehouse=plasticflow_stock_entry_doc.warehouse,
			customs_entry=plasticflow_stock_entry_doc.customs_entry,
			plasticflow_stock_entry=plasticflow_stock_entry_doc.name,
		)
		if plasticflow_stock_entry_doc.customs_entry:
			clear_slot(
				item.product,
				"Customs",
				plasticflow_stock_entry_doc.customs_entry,
				warehouse=None,
				customs_entry=plasticflow_stock_entry_doc.customs_entry,
				plasticflow_stock_entry=plasticflow_stock_entry_doc.name,
			)


def adjust_for_reservation(stock_entry_item, quantity, from_customs=False):
	location_type = "Customs" if from_customs else "Warehouse"
	parent = frappe.get_doc("Plasticflow Stock Entry", stock_entry_item.parent)
	apply_delta(
		stock_entry_item.product,
		location_type,
		parent.name,
		available_delta=-quantity,
		reserved_delta=quantity,
		warehouse=parent.warehouse if not from_customs else None,
		customs_entry=parent.customs_entry,
		plasticflow_stock_entry=parent.name,
	)


def release_reservation(stock_entry_item, quantity, from_customs=False):
	location_type = "Customs" if from_customs else "Warehouse"
	parent = frappe.get_doc("Plasticflow Stock Entry", stock_entry_item.parent)
	apply_delta(
		stock_entry_item.product,
		location_type,
		parent.name,
		available_delta=quantity,
		reserved_delta=-quantity,
		warehouse=parent.warehouse if not from_customs else None,
		customs_entry=parent.customs_entry,
		plasticflow_stock_entry=parent.name,
	)


def issue_stock(stock_entry_item, quantity, from_customs=False):
	location_type = "Customs" if from_customs else "Warehouse"
	parent = frappe.get_doc("Plasticflow Stock Entry", stock_entry_item.parent)
	apply_delta(
		stock_entry_item.product,
		location_type,
		parent.name,
		reserved_delta=-quantity,
		issued_delta=quantity,
		warehouse=parent.warehouse if not from_customs else None,
		customs_entry=parent.customs_entry,
		plasticflow_stock_entry=parent.name,
	)


def reverse_issue(stock_entry_item, quantity, from_customs=False):
	location_type = "Customs" if from_customs else "Warehouse"
	parent = frappe.get_doc("Plasticflow Stock Entry", stock_entry_item.parent)
	apply_delta(
		stock_entry_item.product,
		location_type,
		parent.name,
		reserved_delta=quantity,
		issued_delta=-quantity,
		warehouse=parent.warehouse if not from_customs else None,
		customs_entry=parent.customs_entry,
		plasticflow_stock_entry=parent.name,
	)
