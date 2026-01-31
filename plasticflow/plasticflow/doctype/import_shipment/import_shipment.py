import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

from plasticflow.stock import ledger as stock_ledger

QTY_TOLERANCE = 0.0001
CLEARANCE_FINAL_STATES = {"Cleared", "At Warehouse"}


class ImportShipment(Document):
	"""Commercial shipment covering purchase, logistics, and landed cost inputs."""

	def validate(self):
		self._populate_from_purchase_order()
		self._set_item_defaults()
		self._calculate_totals()
		self._set_clearance_defaults()
		if not getattr(self.flags, "skip_purchase_order_validation", False):
			self._validate_purchase_order_quantities()

	def before_save(self):
		# Allow recalculations on submitted docs
		self.flags.ignore_validate_update_after_submit = True
		self._record_clearance_transition()
		self._calculate_totals()

	def on_update_after_submit(self):
		self.flags.ignore_validate_update_after_submit = True
		self._calculate_totals()

	def on_update(self):
		previous_status = getattr(self.flags, "previous_clearance_status", None)
		current_status = getattr(self.flags, "current_clearance_status", None)

		if getattr(self.flags, "destination_changed", False):
			self._handle_destination_change()

		if previous_status == current_status:
			return
		self._handle_clearance_transition(previous_status, current_status)

	def on_update_after_submit(self):
		"""Allow status-driven stock handling on submitted shipments."""
		self.flags.ignore_validate_update_after_submit = True

		previous_status = getattr(self.flags, "previous_clearance_status", None)
		current_status = self.clearance_status or getattr(self.flags, "current_clearance_status", None) or "In Transit"

		# Fallback to prior doc snapshot if flags weren't set (e.g., db_set or edge updates)
		if previous_status is None:
			before = self.get_doc_before_save()
			if before:
				previous_status = before.clearance_status
				if getattr(self.flags, "current_clearance_status", None) is None:
					self.flags.current_clearance_status = current_status

		if getattr(self.flags, "destination_changed", False):
			self._handle_destination_change()

		if previous_status != current_status or current_status in CLEARANCE_FINAL_STATES:
			self._handle_clearance_transition(previous_status, current_status)

	def on_cancel(self):
		"""Clean up linked stock and ledgers when a shipment is cancelled."""
		self.flags.ignore_validate_update_after_submit = True
		self._cancel_stock_entry()
		stock_ledger.clear_shipment_balances(self)
		self._sync_purchase_order_receipts(exclude_self=True)

	def _populate_from_purchase_order(self):
		po_name = self.purchase_order or self.import_reference
		if not po_name:
			return

		po = frappe.get_doc("Purchase Order", po_name)
		if po.docstatus != 1:
			frappe.throw("Submit the linked purchase order before creating a shipment.")
		self._po_exchange_rate = flt(po.purchase_exchange_rate or 0)
		if self.currency and self.currency != po.purchase_currency:
			frappe.throw("Import currency must match the linked purchase order currency.")

		# Keep both fields in sync for downstream links and UI convenience
		if not self.purchase_order:
			self.purchase_order = po.name
		if not self.import_reference:
			self.import_reference = po.name

		self.currency = po.purchase_currency
		self.local_currency = self.local_currency or po.local_currency
		self.supplier = self.supplier or po.supplier
		self.incoterm = self.incoterm or po.incoterm
		if not self.shipment_date:
			self.shipment_date = po.po_date
		if not self.expected_arrival:
			self.expected_arrival = po.expected_shipment

		if self.items:
			return

		def _allocated_quantity(po_item_name: str) -> float:
			if not po_item_name:
				return 0.0
			row = frappe.db.get_all(
				"Import Shipment Item",
				filters={"purchase_order_item": po_item_name, "docstatus": 1},
				fields=["sum(quantity) as qty"],
			)
			return flt(row[0].qty) if row else 0.0

		def _available_quantity(po_row) -> float:
			ordered = flt(po_row.quantity or 0)
			received = flt(po_row.received_qty or 0)
			allocated = _allocated_quantity(po_row.name)
			return ordered - max(received, allocated)

		for item in po.items:
			pending_qty = _available_quantity(item)
			if pending_qty <= QTY_TOLERANCE:
				continue
			base_rate = flt(item.rate or 0)
			self.append(
				"items",
				{
					"product": item.product,
					"product_name": item.product_name,
					"description": item.description,
					"quantity": pending_qty,
					"uom": item.uom,
					"base_rate": base_rate,
					"purchase_order_item": item.name,
				},
			)

		if po_name and not self.items:
			frappe.throw(
				_("All items on Purchase Order {0} are already allocated to import shipments or received.").format(
					po_name
				)
			)

	def _set_item_defaults(self):
		if not self.currency:
			self.currency = frappe.db.get_default("currency")
		if not self.local_currency:
			self.local_currency = frappe.db.get_default("currency")

		exchange_rate = 1
		if getattr(self, "_po_exchange_rate", None):
			exchange_rate = flt(self._po_exchange_rate or 0)
		elif self.purchase_order:
			exchange_rate = flt(
				frappe.db.get_value("Purchase Order", self.purchase_order, "purchase_exchange_rate") or 0
			)
		if self.currency == self.local_currency:
			exchange_rate = 1

		for item in self.items:
			if item.product and not item.product_name:
				item.product_name = frappe.db.get_value("Product", item.product, "product_name")
			if item.product and not item.uom:
				item.uom = frappe.db.get_value("Product", item.product, "uom")
			quantity = flt(item.quantity or 0)
			base_rate = flt(item.base_rate or 0)
			item.base_amount = quantity * base_rate
			if quantity:
				item.base_rate = base_rate
			if item.landed_cost_amount and quantity:
				item.landed_cost_rate = flt(item.landed_cost_amount) / quantity
			if item.landed_cost_amount_local and quantity:
				item.landed_cost_rate_local = flt(item.landed_cost_amount_local) / quantity
			if exchange_rate > 0:
				item.base_amount_local = flt(item.base_amount) * exchange_rate
			elif self.currency == self.local_currency:
				item.base_amount_local = flt(item.base_amount)
			else:
				item.base_amount_local = 0

	def _calculate_totals(self):
		total_quantity = sum(flt(item.quantity or 0) for item in self.items)
		total_base = sum(flt(item.base_amount or 0) for item in self.items)
		total_landed = sum(flt(item.landed_cost_amount or 0) for item in self.items)
		total_landed_local = sum(flt(item.landed_cost_amount_local or 0) for item in self.items)

		self.total_quantity = total_quantity
		self.total_shipment_amount = total_base
		self.total_landed_cost = total_landed
		self.total_landed_cost_local = total_landed_local
		self.per_unit_landed_cost = flt(total_landed / total_quantity) if total_quantity else 0
		self.per_unit_landed_cost_local = (
			flt(total_landed_local / total_quantity) if total_quantity else 0
		)
		if not self.landing_cost_status:
			self.landing_cost_status = "Draft"

	def _set_clearance_defaults(self):
		self.clearance_status = self.clearance_status or "In Transit"
		if self.clearance_status in CLEARANCE_FINAL_STATES and not self.cleared_on:
			self.cleared_on = nowdate()
		if not self.total_declared_value:
			self.total_declared_value = self.total_shipment_amount or 0

	def _record_clearance_transition(self):
		previous = self.get_doc_before_save()
		prev_status = previous.clearance_status if previous else None
		current_status = self.clearance_status or "In Transit"
		if prev_status != current_status:
			self.flags.previous_clearance_status = prev_status
			self.flags.current_clearance_status = current_status
			if current_status == "Cleared":
				self.cleared_on = nowdate()

		prev_destination = previous.destination_warehouse if previous else None
		if prev_destination != self.destination_warehouse:
			self.flags.destination_changed = True

	def _handle_clearance_transition(self, previous_status, current_status):
		current_status = current_status or self.clearance_status or "In Transit"
		if current_status == previous_status:
			return

		if current_status in CLEARANCE_FINAL_STATES:
			if current_status == "Cleared":
				self.cleared_on = nowdate()
			if current_status == "At Warehouse" and not self.destination_warehouse:
				frappe.throw(_("Destination Warehouse is required before marking the shipment as at warehouse."))
			stock_entry = self._ensure_stock_entry()
			if current_status == "Cleared":
				if stock_entry.status != "At Customs":
					stock_entry.status = "At Customs"
					stock_entry.save(ignore_permissions=True)
				stock_ledger.update_stock_entry_balances(stock_entry)
			else:  # At Warehouse
				self._prepare_stock_entry_for_warehouse(stock_entry)
				stock_ledger.update_stock_entry_balances(stock_entry)
		elif previous_status in CLEARANCE_FINAL_STATES:
			self._rollback_clearance()

	def _handle_destination_change(self):
		if self.clearance_status != "At Warehouse" or not self.stock_entry:
			return
		if not frappe.db.exists("Stock Entries", self.stock_entry):
			return
		stock_entry = frappe.get_doc("Stock Entries", self.stock_entry)
		self._prepare_stock_entry_for_warehouse(stock_entry)
		stock_ledger.update_stock_entry_balances(stock_entry)

	def _ensure_stock_entry(self):
		if self.stock_entry and frappe.db.exists("Stock Entries", self.stock_entry):
			return frappe.get_doc("Stock Entries", self.stock_entry)

		if not self.name:
			# Should not happen because on_update runs post-save, but guard just in case.
			self.save(ignore_permissions=True)

		stock_entry = frappe.new_doc("Stock Entries")
		stock_entry.import_shipment = self.name
		stock_entry.arrival_date = self.arrival_date or nowdate()
		stock_entry.warehouse = self.destination_warehouse
		stock_entry.status = "At Customs"
		stock_entry.insert(ignore_permissions=True)
		if stock_entry.docstatus == 0:
			stock_entry.submit()
		self.db_set("stock_entry", stock_entry.name, update_modified=False)
		return stock_entry

	def _prepare_stock_entry_for_warehouse(self, stock_entry):
		stock_entry.flags.ignore_validate_update_after_submit = True
		updated = False
		if stock_entry.status != "Available":
			stock_entry.status = "Available"
			updated = True
		if self.destination_warehouse and stock_entry.warehouse != self.destination_warehouse:
			stock_entry.warehouse = self.destination_warehouse
			updated = True
		if not stock_entry.arrival_date:
			stock_entry.arrival_date = nowdate()
			updated = True
		if updated:
			stock_entry.save(ignore_permissions=True)
		return stock_entry

	def _rollback_clearance(self):
		if self.stock_entry and frappe.db.exists("Stock Entries", self.stock_entry):
			stock_entry = frappe.get_doc("Stock Entries", self.stock_entry)
			if stock_entry.status != "At Customs":
				stock_entry.status = "At Customs"
				stock_entry.save(ignore_permissions=True)
			stock_ledger.update_stock_entry_balances(stock_entry)
		else:
			stock_ledger.sync_shipment_customs_balances(self)

		if self.clearance_status not in CLEARANCE_FINAL_STATES and self.cleared_on:
			self.db_set("cleared_on", None, update_modified=False)

	def _cancel_stock_entry(self):
		if not self.stock_entry or not frappe.db.exists("Stock Entries", self.stock_entry):
			return

		stock_entry = frappe.get_doc("Stock Entries", self.stock_entry)
		stock_entry.flags.ignore_validate_update_after_submit = True

		if stock_entry.docstatus == 1:
			stock_entry.cancel()
		elif stock_entry.docstatus == 0:
			stock_entry.delete(ignore_permissions=True)

		self.db_set("stock_entry", None, update_modified=False)

	def _validate_purchase_order_quantities(self):
		"""Guard against over-allocating shipments beyond purchase order availability."""
		if not self.purchase_order:
			return

		# Keep Purchase Order received_qty in sync with submitted import shipments so stale values
		# (e.g., cancelled or amended shipments) don't block new partial shipments.
		po_shipment_qty = self._sync_purchase_order_receipts(exclude_self=True)

		po_items = frappe.db.get_all(
			"Purchase Order Item",
			filters={"parent": self.purchase_order},
			fields=["name", "product", "product_name", "quantity", "received_qty"],
		)
		if not po_items:
			return

		po_map = {row.name: row for row in po_items}

		for row in self.items:
			if not row.purchase_order_item or row.purchase_order_item not in po_map:
				continue

			po_row = po_map[row.purchase_order_item]
			ordered = flt(po_row.quantity or 0)
			allocated_qty = po_shipment_qty.get(row.purchase_order_item, 0.0)

			available = max(ordered - allocated_qty, 0)
			requested = flt(row.quantity or 0)

			if requested - available > QTY_TOLERANCE:
				product_label = row.product_name or row.product or row.purchase_order_item
				frappe.throw(
					_(
						"Quantity {0} for product {1} exceeds remaining {2} on Purchase Order {3} "
						"(ordered {4}, already in other submitted shipments {5})."
					).format(
						frappe.format(requested, {"fieldtype": "Float"}),
						product_label,
						frappe.format(available if available > 0 else 0, {"fieldtype": "Float"}),
						self.purchase_order,
						frappe.format(ordered, {"fieldtype": "Float"}),
						frappe.format(allocated_qty, {"fieldtype": "Float"}),
					)
				)

	def _sync_purchase_order_receipts(self, *, exclude_self: bool = False) -> dict[str, float]:
		"""Align Purchase Order received_qty with submitted import shipments.

		Returns a map of purchase_order_item -> total submitted shipment qty.
		"""
		if not self.purchase_order:
			return {}

		params = [self.purchase_order]
		exclude_clause = ""
		if exclude_self and self.name:
			exclude_clause = "and ish.name != %s"
			params.append(self.name)

		rows = frappe.db.sql(
			f"""
			select
				isi.purchase_order_item as po_item,
				coalesce(sum(isi.quantity), 0) as qty
			from `tabImport Shipment Item` isi
			inner join `tabImport Shipment` ish on ish.name = isi.parent
			where ish.purchase_order = %s
				and ish.docstatus = 1
				{exclude_clause}
			group by isi.purchase_order_item
			""",
			tuple(params),
			as_dict=True,
		)
		qty_map = {row.po_item: flt(row.qty) for row in rows if row.po_item}

		po_items = frappe.db.get_all(
			"Purchase Order Item",
			filters={"parent": self.purchase_order},
			fields=["name", "quantity", "received_qty"],
		)

		updated = False
		for item in po_items:
			target_qty = min(qty_map.get(item.name, 0.0), flt(item.quantity or 0))
			if abs(flt(item.received_qty or 0) - target_qty) > QTY_TOLERANCE:
				frappe.db.set_value(
					"Purchase Order Item",
					item.name,
					"received_qty",
					target_qty,
					update_modified=False,
				)
				updated = True

		if updated:
			po_doc = frappe.get_doc("Purchase Order", self.purchase_order)
			po_doc.reload()
			po_doc.update_receipt_status()

		return qty_map


def get_dashboard_data():
	return {
		"fieldname": "import_shipment",
		"transactions": [
			{"label": _("Costing"), "items": ["Landing Cost Worksheet"]},
			{"label": _("Customs & Stock"), "items": ["Stock Entries"]},
		],
		"internal_links": {
			"Purchase Order": ["purchase_order"],
		},
	}


@frappe.whitelist()
def create_landing_cost_worksheet(import_shipment: str):
	if not import_shipment:
		frappe.throw(_("Import Shipment is required."))

	shipment = frappe.get_doc("Import Shipment", import_shipment)
	shipment.check_permission("read")

	if shipment.docstatus == 2:
		frappe.throw(_("Cannot create a landing cost worksheet for a cancelled import shipment."))

	existing = frappe.db.get_value(
		"Landing Cost Worksheet",
		{
			"import_shipment": shipment.name,
			"docstatus": ["!=", 2],
		},
		"name",
	)

	if existing:
		return {"name": existing, "status": "existing"}

	worksheet = frappe.new_doc("Landing Cost Worksheet")
	worksheet.import_shipment = shipment.name
	worksheet.purchase_order = shipment.purchase_order
	worksheet.posting_date = nowdate()
	worksheet.insert(ignore_permissions=True)

	return {"name": worksheet.name, "status": "created"}


@frappe.whitelist()
def create_sales_order_from_shipment(import_shipment: str, customer: str, sales_type: str = "Cash", delivery_source: str = "Warehouse"):
	if not import_shipment:
		frappe.throw(_("Import Shipment is required."))
	if not customer:
		frappe.throw(_("Customer is required to create a Sales Order."))

	shipment = frappe.get_doc("Import Shipment", import_shipment)
	if shipment.docstatus == 2:
		frappe.throw(_("Cannot create a Sales Order from a cancelled shipment."))

	so = frappe.new_doc("Sales Order")
	so.customer = customer
	so.import_shipment = shipment.name
	so.delivery_source = delivery_source or "Warehouse"
	so.sales_type = sales_type or "Cash"
	so.currency = frappe.db.get_default("currency") or "ETB"
	so.apply_withholding = 1
	so.withholding_rate = 3
	so.order_date = nowdate()

	for item in shipment.items:
		if not item.product or not item.quantity:
			continue
		so.append(
			"items",
			{
				"product": item.product,
				"product_name": item.product_name,
				"description": item.description,
				"quantity": item.quantity,
				"uom": item.uom,
				"import_shipment_item": item.name,
				"rate": item.landed_cost_rate_local or item.base_rate or 0,
			},
		)

	if not so.items:
		frappe.throw(_("No shippable items found on Import Shipment {0}.").format(shipment.name))

	so.insert(ignore_permissions=True)
	return {"name": so.name, "doctype": so.doctype}
