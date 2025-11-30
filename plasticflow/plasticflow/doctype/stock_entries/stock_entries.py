import frappe
from frappe.model.document import Document
from frappe.utils import nowdate

from plasticflow.stock import ledger as stock_ledger


class StockEntries(Document):
	"""Represents stock entry tracking movement between customs and warehouses."""

	def validate(self):
		self._populate_from_import_shipment()
		self._update_item_balances()
		self._update_totals()
		self._set_status()

	def before_insert(self):
		self._populate_from_import_shipment()

	def before_save(self):
		self._assign_item_row_names()

	def _populate_from_import_shipment(self):
		if not self.import_shipment or not frappe.db.exists("Import Shipment", self.import_shipment):
			return

		shipment = frappe.get_doc("Import Shipment", self.import_shipment)
		self.import_currency = shipment.currency
		self.local_currency = shipment.local_currency or frappe.db.get_default("currency") or shipment.currency

		if not self.arrival_date:
			self.arrival_date = shipment.arrival_date or nowdate()

		if shipment.destination_warehouse and not self.warehouse:
			self.warehouse = shipment.destination_warehouse

		if not self.items:
			for item in shipment.items:
				quantity = item.quantity or 0
				landed_amount = item.landed_cost_amount or 0
				landed_amount_local = item.landed_cost_amount_local or 0
				landed_rate = item.landed_cost_rate or (landed_amount / quantity if quantity else 0)
				landed_rate_local = item.landed_cost_rate_local or (landed_amount_local / quantity if quantity else 0)

				self.append(
					"items",
					{
						"product": item.product,
						"product_name": item.product_name,
						"received_qty": quantity,
						"reserved_qty": 0,
						"issued_qty": 0,
						"uom": item.uom,
						"warehouse_location": item.warehouse_location,
						"import_shipment_item": item.name,
						"purchase_order_item": item.purchase_order_item,
						"landed_cost_rate": landed_rate,
						"landed_cost_amount": landed_amount,
						"landed_cost_rate_local": landed_rate_local,
						"landed_cost_amount_local": landed_amount_local,
					},
				)

		if not self.status:
			clearance_status = shipment.clearance_status or "In Transit"
			self.status = "Available" if clearance_status == "At Warehouse" else "At Customs"

	def _update_item_balances(self):
		for item in self.items:
			received = item.received_qty or 0
			reserved = item.reserved_qty or 0
			issued = item.issued_qty or 0
			item.available_qty = max(received - reserved - issued, 0)

	def _update_totals(self):
		self.total_received_qty = sum((item.received_qty or 0) for item in self.items)
		self.total_reserved_qty = sum((item.reserved_qty or 0) for item in self.items)
		self.total_issued_qty = sum((item.issued_qty or 0) for item in self.items)
		self.available_qty = sum((item.available_qty or 0) for item in self.items)

	def _set_status(self):
		if self.status == "At Customs":
			return
		if self.available_qty <= 0 and (self.total_issued_qty or 0):
			self.status = "Depleted"
		elif self.available_qty <= 0 and not self.total_issued_qty:
			self.status = "Reserved"
		elif self.total_reserved_qty:
			self.status = "Reserved"
		elif self.available_qty and self.total_issued_qty:
			self.status = "Partially Issued"
		else:
			self.status = "Available"

	def on_submit(self):
		self._link_to_shipment()
		stock_ledger.update_stock_entry_balances(self)

	def on_update_after_submit(self):
		self._link_to_shipment()
		stock_ledger.update_stock_entry_balances(self)

	def on_cancel(self):
		stock_ledger.clear_stock_entry(self)
		if self.import_shipment and frappe.db.exists("Import Shipment", self.import_shipment):
			frappe.db.set_value(
				"Import Shipment",
				self.import_shipment,
				"stock_entry",
				None,
				update_modified=False,
			)

	def _link_to_shipment(self):
		if not self.import_shipment or not self.name:
			return
		if frappe.db.exists("Import Shipment", self.import_shipment):
			frappe.db.set_value(
				"Import Shipment",
				self.import_shipment,
				"stock_entry",
				self.name,
				update_modified=False,
			)

	def _assign_item_row_names(self):
		"""Give stock entry items deterministic identifiers for FIFO tracking."""
		if not self.name or self.name.startswith("New "):
			return

		prefix = f"{self.name}-BATCH-"
		existing_sequences = []
		for row in self.items:
			sequence = self._extract_child_sequence(row.name, prefix)
			if sequence is not None:
				existing_sequences.append(sequence)

		next_sequence = (max(existing_sequences) if existing_sequences else 0) + 1

		for row in self.items:
			if row.name and not row.name.startswith("new-"):
				continue
			row.name = f"{prefix}{next_sequence:03d}"
			next_sequence += 1

	@staticmethod
	def _extract_child_sequence(value, prefix):
		if not value or not value.startswith(prefix):
			return None
		suffix = value[len(prefix) :]
		return int(suffix) if suffix.isdigit() else None
