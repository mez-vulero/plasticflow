import frappe
from frappe.utils import now_datetime

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
	filters = _get_filters(product, location_type, location_reference, warehouse, customs_entry, plasticflow_stock_entry)
	name = frappe.db.get_value(LEDGER_DOCTYPE, filters)
	if name:
		doc = frappe.get_doc(LEDGER_DOCTYPE, name)
	else:
		doc = frappe.new_doc(LEDGER_DOCTYPE)
		doc.update(filters)
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
):
	"""Adjust balances by delta values."""
	doc = _get_or_create(product, location_type, location_reference, warehouse, customs_entry, plasticflow_stock_entry)
	doc.available_qty = max((doc.available_qty or 0) + available_delta, 0)
	doc.reserved_qty = max((doc.reserved_qty or 0) + reserved_delta, 0)
	doc.issued_qty = max((doc.issued_qty or 0) + issued_delta, 0)
	doc.last_movement = now_datetime()
	if doc.is_new():
		doc.insert(ignore_permissions=True)
	else:
		doc.save(ignore_permissions=True)
	return doc


def clear_slot(product, location_type, location_reference, warehouse=None, customs_entry=None, plasticflow_stock_entry=None):
	name = frappe.db.get_value(
		LEDGER_DOCTYPE,
		_get_filters(product, location_type, location_reference, warehouse, customs_entry, plasticflow_stock_entry),
	)
	if name:
		frappe.delete_doc(LEDGER_DOCTYPE, name, ignore_permissions=True, force=1, delete_permanently=True)


# Convenience helpers -----------------------------------------------------

def sync_customs_entry(customs_entry_doc):
	for item in customs_entry_doc.items:
		set_balances(
			item.product,
			"Customs",
			customs_entry_doc.name,
			available=item.quantity or 0,
			warehouse=None,
			customs_entry=customs_entry_doc.name,
			plasticflow_stock_entry=customs_entry_doc.plasticflow_stock_entry,
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


def transfer_customs_to_warehouse(customs_entry_doc, plasticflow_stock_entry_doc):
	for item in plasticflow_stock_entry_doc.items:
		qty = item.available_qty or item.received_qty or 0
		if not qty:
			continue

		# set customs balances to zero for this entry
		set_balances(
			item.product,
			"Customs",
			customs_entry_doc.name,
			available=0,
			reserved=0,
			issued=0,
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
