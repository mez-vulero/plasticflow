import frappe
from frappe.utils import flt, now_datetime

LEDGER_DOCTYPE = "Plasticflow Stock Ledger Entry"


def _get_filters(
	product,
	location_type,
	location_reference,
	warehouse=None,
	stock_entry=None,
	import_shipment=None,
):
	filters = {
		"product": product,
		"location_type": location_type,
		"location_reference": location_reference,
	}
	if warehouse:
		filters["warehouse"] = warehouse
	if stock_entry:
		filters["stock_entry"] = stock_entry
	if import_shipment:
		filters["import_shipment"] = import_shipment
	return filters


def _get_or_create(
	product,
	location_type,
	location_reference,
	warehouse=None,
	stock_entry=None,
	import_shipment=None,
):
	base_filters = _get_filters(
		product,
		location_type,
		location_reference,
		warehouse,
		None,
		import_shipment,
	)
	base_filters.pop("stock_entry", None)

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
	doc.stock_entry = stock_entry
	doc.import_shipment = import_shipment

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
	stock_entry=None,
	import_shipment=None,
	landed_cost_rate=None,
	landed_cost_amount=None,
	remarks=None,
):
	"""Set absolute balances for a ledger slot."""
	doc = _get_or_create(
		product,
		location_type,
		location_reference,
		warehouse,
		stock_entry,
		import_shipment,
	)
	if available is not None:
		doc.available_qty = available
	if reserved is not None:
		doc.reserved_qty = reserved
	if issued is not None:
		doc.issued_qty = issued
	if remarks is not None:
		doc.remarks = remarks
	if landed_cost_rate is not None:
		doc.landed_cost_rate = landed_cost_rate
	if landed_cost_amount is not None:
		doc.landed_cost_amount = landed_cost_amount
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
	stock_entry=None,
	import_shipment=None,
	remarks=None,
):
	"""Adjust balances by delta values."""
	doc = _get_or_create(
		product,
		location_type,
		location_reference,
		warehouse,
		stock_entry,
		import_shipment,
	)
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


def clear_slot(
	product,
	location_type,
	location_reference,
	warehouse=None,
	stock_entry=None,
	import_shipment=None,
):
	base_filters = _get_filters(product, location_type, location_reference, warehouse, None, import_shipment)
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


def get_available_quantity_by_shipment(product, *, location_type, import_shipment, warehouse=None):
	"""Return available qty for a product filtered by shipment."""
	if not import_shipment:
		return get_available_quantity(product, location_type=location_type, warehouse=warehouse)

	filters = {
		"product": product,
		"location_type": location_type,
		"import_shipment": import_shipment,
	}
	if warehouse:
		filters["warehouse"] = warehouse
	rows = frappe.db.get_all(
		LEDGER_DOCTYPE,
		filters=filters,
		fields=["coalesce(sum(available_qty), 0) as available"],
	)
	return flt(rows[0].available) if rows else 0.0


def _get_transferred_totals_by_shipment_item(import_shipment_name):
	rows = frappe.db.sql(
		"""
		select
			sei.import_shipment_item as shipment_item,
			coalesce(sum(sei.received_qty), 0) as total_transferred
		from `tabStock Entry Items` sei
		inner join `tabStock Entries` se on se.name = sei.parent
		where se.docstatus = 1
			and se.import_shipment = %s
			and se.status != 'At Customs'
		group by sei.import_shipment_item
		""",
		(import_shipment_name,),
		as_dict=True,
	)
	return {row.shipment_item: row.total_transferred for row in rows}


def sync_shipment_customs_balances(shipment_doc, *, stock_entry=None):
	linked_entry = stock_entry
	if not linked_entry and shipment_doc.get("stock_entry"):
		linked_entry = frappe.get_doc("Stock Entries", shipment_doc.stock_entry)

	source_items = linked_entry.items if linked_entry else shipment_doc.items
	customs_reference = shipment_doc.name

	for item in source_items:
		local_rate = getattr(item, "landed_cost_rate_local", None)
		local_amount = getattr(item, "landed_cost_amount_local", None)
		if local_rate is None:
			local_rate = getattr(item, "landed_cost_rate", 0)
		if local_amount is None:
			local_amount = getattr(item, "landed_cost_amount", 0)
		quantity = getattr(item, "available_qty", None)
		if quantity is None:
			quantity = getattr(item, "received_qty", None)
		if quantity is None:
			quantity = getattr(item, "quantity", 0)

		set_balances(
			item.product,
			"Customs",
			customs_reference,
			available=quantity or 0,
			reserved=0,
			issued=0,
			warehouse=None,
			stock_entry=linked_entry.name if linked_entry else None,
			import_shipment=shipment_doc.name,
			landed_cost_rate=local_rate,
			landed_cost_amount=local_amount,
			remarks="Customs stock awaiting transfer",
		)


def clear_shipment_balances(shipment_doc):
	for item in shipment_doc.items:
		clear_slot(
			item.product,
			"Customs",
			shipment_doc.name,
			warehouse=None,
			import_shipment=shipment_doc.name,
			stock_entry=shipment_doc.get("stock_entry"),
		)


def _set_warehouse_balances(stock_entry_doc):
	for item in stock_entry_doc.items:
		local_rate = getattr(item, "landed_cost_rate_local", None)
		local_amount = getattr(item, "landed_cost_amount_local", None)
		if local_rate is None:
			local_rate = getattr(item, "landed_cost_rate", 0)
		if local_amount is None:
			local_amount = getattr(item, "landed_cost_amount", 0)
		set_balances(
			item.product,
			"Warehouse",
			stock_entry_doc.name,
			available=item.available_qty or item.received_qty or 0,
			warehouse=stock_entry_doc.warehouse,
			stock_entry=stock_entry_doc.name,
			import_shipment=stock_entry_doc.import_shipment,
			landed_cost_rate=local_rate,
			landed_cost_amount=local_amount,
			remarks="Stock available in warehouse",
		)


def update_warehouse_stock(stock_entry_doc):
	for item in stock_entry_doc.items:
		local_rate = getattr(item, "landed_cost_rate_local", None)
		local_amount = getattr(item, "landed_cost_amount_local", None)
		if local_rate is None:
			local_rate = getattr(item, "landed_cost_rate", 0)
		if local_amount is None:
			local_amount = getattr(item, "landed_cost_amount", 0)
		set_balances(
			item.product,
			"Warehouse",
			stock_entry_doc.name,
			available=item.available_qty or item.received_qty or 0,
			reserved=item.reserved_qty or 0,
			issued=item.issued_qty or 0,
			warehouse=stock_entry_doc.warehouse,
			stock_entry=stock_entry_doc.name,
			import_shipment=stock_entry_doc.import_shipment,
			landed_cost_rate=local_rate,
			landed_cost_amount=local_amount,
			remarks="Stock available in warehouse",
		)


def transfer_shipment_to_warehouse(shipment_doc, stock_entry_doc):
	shipment_item_map = {child.name: (child.quantity or 0) for child in shipment_doc.items}
	transferred_totals = _get_transferred_totals_by_shipment_item(shipment_doc.name)

	for item in stock_entry_doc.items:
		local_rate = getattr(item, "landed_cost_rate_local", None)
		local_amount = getattr(item, "landed_cost_amount_local", None)
		if local_rate is None:
			local_rate = getattr(item, "landed_cost_rate", 0)
		if local_amount is None:
			local_amount = getattr(item, "landed_cost_amount", 0)
		qty = item.available_qty or item.received_qty or 0
		if not qty:
			continue

		customs_qty = shipment_item_map.get(item.import_shipment_item)
		if customs_qty is None:
			customs_qty = item.received_qty or item.available_qty or 0
		total_transferred = transferred_totals.get(item.import_shipment_item, 0)
		remaining_at_customs = max(customs_qty - total_transferred, 0)

		# update customs balances with remaining stock and record movement in issued qty
		set_balances(
			item.product,
			"Customs",
			shipment_doc.name,
			available=remaining_at_customs,
			reserved=0,
			issued=total_transferred,
			warehouse=None,
			stock_entry=stock_entry_doc.name,
			import_shipment=shipment_doc.name,
			landed_cost_rate=local_rate,
			landed_cost_amount=local_amount,
			remarks="Transferred to warehouse",
		)

		# set warehouse balances to current entry values
		set_balances(
			item.product,
			"Warehouse",
			stock_entry_doc.name,
			available=item.available_qty or item.received_qty or 0,
			reserved=item.reserved_qty or 0,
			issued=item.issued_qty or 0,
			warehouse=stock_entry_doc.warehouse,
			stock_entry=stock_entry_doc.name,
			import_shipment=shipment_doc.name,
			landed_cost_rate=local_rate,
			landed_cost_amount=local_amount,
			remarks="Stock available in warehouse",
		)


def _sync_entry_customs_balances(stock_entry_doc):
	customs_reference = stock_entry_doc.import_shipment or stock_entry_doc.name
	for item in stock_entry_doc.items:
		local_rate = getattr(item, "landed_cost_rate_local", None)
		local_amount = getattr(item, "landed_cost_amount_local", None)
		if local_rate is None:
			local_rate = getattr(item, "landed_cost_rate", 0)
		if local_amount is None:
			local_amount = getattr(item, "landed_cost_amount", 0)
		set_balances(
			item.product,
			"Customs",
			customs_reference,
			available=item.available_qty or item.received_qty or 0,
			reserved=0,
			issued=0,
			warehouse=None,
			stock_entry=stock_entry_doc.name,
			import_shipment=stock_entry_doc.import_shipment,
			landed_cost_rate=local_rate,
			landed_cost_amount=local_amount,
			remarks="Customs stock awaiting transfer",
		)


def update_stock_entry_balances(stock_entry_doc):
	shipment = None
	if stock_entry_doc.import_shipment and frappe.db.exists("Import Shipment", stock_entry_doc.import_shipment):
		shipment = frappe.get_doc("Import Shipment", stock_entry_doc.import_shipment)

	if stock_entry_doc.status == "At Customs":
		if shipment:
			sync_shipment_customs_balances(shipment, stock_entry=stock_entry_doc)
		else:
			_sync_entry_customs_balances(stock_entry_doc)
		for item in stock_entry_doc.items:
			clear_slot(
				item.product,
				"Warehouse",
				stock_entry_doc.name,
				warehouse=stock_entry_doc.warehouse,
				stock_entry=stock_entry_doc.name,
				import_shipment=stock_entry_doc.import_shipment,
			)
		return

	if shipment:
		transfer_shipment_to_warehouse(shipment, stock_entry_doc)
	else:
		update_warehouse_stock(stock_entry_doc)
		customs_reference = stock_entry_doc.import_shipment or stock_entry_doc.name
		for item in stock_entry_doc.items:
			clear_slot(
				item.product,
				"Customs",
				customs_reference,
				warehouse=None,
				stock_entry=stock_entry_doc.name,
				import_shipment=stock_entry_doc.import_shipment,
			)


def clear_stock_entry(stock_entry_doc):
	for item in stock_entry_doc.items:
		clear_slot(
			item.product,
			"Warehouse",
			stock_entry_doc.name,
			warehouse=stock_entry_doc.warehouse,
			stock_entry=stock_entry_doc.name,
			import_shipment=stock_entry_doc.import_shipment,
		)
		customs_reference = stock_entry_doc.import_shipment or stock_entry_doc.name
		if customs_reference:
			clear_slot(
				item.product,
				"Customs",
				customs_reference,
				warehouse=None,
				stock_entry=stock_entry_doc.name,
				import_shipment=stock_entry_doc.import_shipment,
			)


def adjust_for_reservation(stock_entry_item, quantity, from_customs=False):
	location_type = "Customs" if from_customs else "Warehouse"
	parent = frappe.get_doc("Stock Entries", stock_entry_item.parent)
	location_reference = parent.import_shipment if from_customs else parent.name
	apply_delta(
		stock_entry_item.product,
		location_type,
		location_reference,
		available_delta=-quantity,
		reserved_delta=quantity,
		warehouse=parent.warehouse if not from_customs else None,
		stock_entry=parent.name,
		import_shipment=parent.import_shipment,
	)


def release_reservation(stock_entry_item, quantity, from_customs=False):
	location_type = "Customs" if from_customs else "Warehouse"
	parent = frappe.get_doc("Stock Entries", stock_entry_item.parent)
	location_reference = parent.import_shipment if from_customs else parent.name
	apply_delta(
		stock_entry_item.product,
		location_type,
		location_reference,
		available_delta=quantity,
		reserved_delta=-quantity,
		warehouse=parent.warehouse if not from_customs else None,
		stock_entry=parent.name,
		import_shipment=parent.import_shipment,
	)


def issue_stock(stock_entry_item, quantity, from_customs=False):
	location_type = "Customs" if from_customs else "Warehouse"
	parent = frappe.get_doc("Stock Entries", stock_entry_item.parent)
	location_reference = parent.import_shipment if from_customs else parent.name
	apply_delta(
		stock_entry_item.product,
		location_type,
		location_reference,
		reserved_delta=-quantity,
		issued_delta=quantity,
		warehouse=parent.warehouse if not from_customs else None,
		stock_entry=parent.name,
		import_shipment=parent.import_shipment,
	)


def reverse_issue(stock_entry_item, quantity, from_customs=False):
	location_type = "Customs" if from_customs else "Warehouse"
	parent = frappe.get_doc("Stock Entries", stock_entry_item.parent)
	location_reference = parent.import_shipment if from_customs else parent.name
	apply_delta(
		stock_entry_item.product,
		location_type,
		location_reference,
		reserved_delta=quantity,
		issued_delta=-quantity,
		warehouse=parent.warehouse if not from_customs else None,
		stock_entry=parent.name,
		import_shipment=parent.import_shipment,
	)
