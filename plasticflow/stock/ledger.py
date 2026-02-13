import frappe
from frappe.utils import flt, now_datetime

LEDGER_DOCTYPE = "Stock Ledger Entry"
MOVEMENT_DOCTYPE = "Stock Ledger Movement"
MOVEMENT_TOLERANCE = 0.0001


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
	source_doctype=None,
	source_name=None,
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
	old_available = flt(doc.available_qty or 0)
	old_reserved = flt(doc.reserved_qty or 0)
	old_issued = flt(doc.issued_qty or 0)

	new_available = old_available if available is None else flt(available)
	new_reserved = old_reserved if reserved is None else flt(reserved)
	new_issued = old_issued if issued is None else flt(issued)

	doc.available_qty = new_available
	doc.reserved_qty = new_reserved
	doc.issued_qty = new_issued
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
	_log_movement(
		product,
		location_type,
		location_reference,
		warehouse=warehouse,
		stock_entry=stock_entry,
		import_shipment=import_shipment,
		available_delta=new_available - old_available,
		reserved_delta=new_reserved - old_reserved,
		issued_delta=new_issued - old_issued,
		balance_available=new_available,
		balance_reserved=new_reserved,
		balance_issued=new_issued,
		remarks=remarks,
		source_doctype=source_doctype,
		source_name=source_name,
	)
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
	source_doctype=None,
	source_name=None,
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
	old_available = flt(doc.available_qty or 0)
	old_reserved = flt(doc.reserved_qty or 0)
	old_issued = flt(doc.issued_qty or 0)

	new_available = max(old_available + flt(available_delta or 0), 0)
	new_reserved = max(old_reserved + flt(reserved_delta or 0), 0)
	new_issued = max(old_issued + flt(issued_delta or 0), 0)

	doc.available_qty = new_available
	doc.reserved_qty = new_reserved
	doc.issued_qty = new_issued
	if remarks is not None:
		doc.remarks = remarks
	doc.last_movement = now_datetime()
	if doc.is_new():
		doc.insert(ignore_permissions=True)
	else:
		doc.save(ignore_permissions=True)
	_log_movement(
		product,
		location_type,
		location_reference,
		warehouse=warehouse,
		stock_entry=stock_entry,
		import_shipment=import_shipment,
		available_delta=new_available - old_available,
		reserved_delta=new_reserved - old_reserved,
		issued_delta=new_issued - old_issued,
		balance_available=new_available,
		balance_reserved=new_reserved,
		balance_issued=new_issued,
		remarks=remarks,
		source_doctype=source_doctype,
		source_name=source_name,
	)
	return doc


def _log_movement(
	product,
	location_type,
	location_reference,
	*,
	warehouse=None,
	stock_entry=None,
	import_shipment=None,
	available_delta=0.0,
	reserved_delta=0.0,
	issued_delta=0.0,
	balance_available=0.0,
	balance_reserved=0.0,
	balance_issued=0.0,
	remarks=None,
	source_doctype=None,
	source_name=None,
):
	if (
		abs(available_delta) < MOVEMENT_TOLERANCE
		and abs(reserved_delta) < MOVEMENT_TOLERANCE
		and abs(issued_delta) < MOVEMENT_TOLERANCE
	):
		return
	if not frappe.db.table_exists(MOVEMENT_DOCTYPE):
		return

	doc = frappe.new_doc(MOVEMENT_DOCTYPE)
	doc.product = product
	doc.location_type = location_type
	doc.location_reference = location_reference
	doc.warehouse = warehouse
	doc.stock_entry = stock_entry
	doc.import_shipment = import_shipment
	doc.available_delta = available_delta
	doc.reserved_delta = reserved_delta
	doc.issued_delta = issued_delta
	doc.balance_available = balance_available
	doc.balance_reserved = balance_reserved
	doc.balance_issued = balance_issued
	if remarks is not None:
		doc.remarks = remarks
	if source_doctype:
		doc.source_doctype = source_doctype
	if source_name:
		doc.source_name = source_name
	doc.insert(ignore_permissions=True)


def clear_slot(
	product,
	location_type,
	location_reference,
	warehouse=None,
	stock_entry=None,
	import_shipment=None,
):
	base_filters = _get_filters(product, location_type, location_reference, warehouse, None, import_shipment)
	entries = frappe.db.get_all(
		LEDGER_DOCTYPE,
		filters=base_filters,
		fields=[
			"name",
			"product",
			"location_type",
			"location_reference",
			"warehouse",
			"stock_entry",
			"import_shipment",
			"available_qty",
			"reserved_qty",
			"issued_qty",
		],
	)
	for entry in entries:
		available = flt(entry.available_qty or 0)
		reserved = flt(entry.reserved_qty or 0)
		issued = flt(entry.issued_qty or 0)
		_log_movement(
			entry.product,
			entry.location_type,
			entry.location_reference,
			warehouse=entry.warehouse,
			stock_entry=entry.stock_entry,
			import_shipment=entry.import_shipment,
			available_delta=-available,
			reserved_delta=-reserved,
			issued_delta=-issued,
			balance_available=0,
			balance_reserved=0,
			balance_issued=0,
			remarks="Cleared ledger slot",
		)
		frappe.delete_doc(
			LEDGER_DOCTYPE,
			entry.name,
			ignore_permissions=True,
			force=1,
			delete_permanently=True,
		)


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
		available_qty = _available_from_item(item)
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
			available=available_qty,
			warehouse=stock_entry_doc.warehouse,
			stock_entry=stock_entry_doc.name,
			import_shipment=stock_entry_doc.import_shipment,
			landed_cost_rate=local_rate,
			landed_cost_amount=local_amount,
			remarks="Stock available in warehouse",
		)


def update_warehouse_stock(stock_entry_doc):
	for item in stock_entry_doc.items:
		available_qty = _available_from_item(item)
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
			available=available_qty,
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
		available_qty = _available_from_item(item)
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
			available=available_qty,
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
		available_qty = _available_from_item(item)
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
			available=available_qty,
			reserved=0,
			issued=0,
			warehouse=None,
			stock_entry=stock_entry_doc.name,
			import_shipment=stock_entry_doc.import_shipment,
			landed_cost_rate=local_rate,
			landed_cost_amount=local_amount,
			remarks="Customs stock awaiting transfer",
		)


def _available_from_item(item) -> float:
	"""Compute current available qty from a stock entry item."""
	received = flt(getattr(item, "received_qty", 0) or getattr(item, "available_qty", 0))
	reserved = flt(getattr(item, "reserved_qty", 0))
	issued = flt(getattr(item, "issued_qty", 0))
	available = received - reserved - issued
	return max(available, 0)


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
