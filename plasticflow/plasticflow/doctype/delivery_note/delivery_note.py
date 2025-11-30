import frappe
from frappe.model.document import Document
from frappe.utils import flt, nowdate

from plasticflow.stock import ledger as stock_ledger


class DeliveryNote(Document):
	"""Final logistics document that confirms delivery of materials."""

	def validate(self):
		self._set_item_defaults()
		self.total_quantity = sum((item.quantity or 0) for item in self.items)
		if not self.delivery_date:
			self.delivery_date = nowdate()

	def before_submit(self):
		if self.status == "Draft":
			self.status = "In Transit"

	def on_submit(self):
		self._issue_stock()
		if self.status == "In Transit":
			self.db_set("status", "In Transit")
		else:
			self.db_set("status", self.status)
		frappe.db.set_value("Sales Order", self.sales_order, "status", "Completed")
		frappe.db.set_value("Gate Pass", self.gate_pass, "status", "Closed")

	def on_update_after_submit(self):
		if self.status == "Delivered":
			frappe.db.set_value("Sales Order", self.sales_order, "status", "Completed")

	def on_cancel(self):
		self._reverse_stock()
		self.db_set("status", "Cancelled")
		if self.sales_order and frappe.db.exists("Sales Order", self.sales_order):
			frappe.db.set_value(
				"Sales Order",
				self.sales_order,
				{"status": "Invoiced", "delivery_note": None},
				update_modified=False,
			)
		if self.gate_pass and frappe.db.exists("Gate Pass", self.gate_pass):
			frappe.db.set_value(
				"Gate Pass",
				self.gate_pass,
				{"status": "Issued", "delivery_note": None},
				update_modified=False,
			)

	def _set_item_defaults(self):
		for item in self.items:
			if item.product and not item.product_name:
				item.product_name = frappe.db.get_value("Product", item.product, "product_name")

	def _issue_stock(self):
		batch_map = {}
		aggregated = []
		for item in self.items:
			if item.stock_entry_item:
				child = frappe.get_doc("Stock Entry Items", item.stock_entry_item)
				batch_map.setdefault(child.parent, []).append((child.name, item.quantity or 0))
			else:
				aggregated.append(item)

		for batch_name, entries in batch_map.items():
			batch = frappe.get_doc("Stock Entries", batch_name)
			updated = False
			from_customs = batch.status == "At Customs"
			for child_name, qty in entries:
				child = next((row for row in batch.items if row.name == child_name), None)
				if not child:
					continue
				child.reserved_qty = max((child.reserved_qty or 0) - qty, 0)
				child.issued_qty = (child.issued_qty or 0) + qty
				stock_ledger.issue_stock(child, qty, from_customs=from_customs)
				updated = True
			if updated:
				batch.save(ignore_permissions=True)

		if aggregated:
			location_type, warehouse = self._source_location()
			reference = self._ledger_reference(location_type, warehouse)
			for item in aggregated:
				qty = flt(item.quantity or 0)
				if qty <= 0 or not item.product:
					continue
				stock_ledger.apply_delta(
					item.product,
					location_type,
					reference,
					reserved_delta=-qty,
					issued_delta=qty,
					warehouse=warehouse if location_type == "Warehouse" else None,
					remarks=f"Issued via Delivery Note {self.name}",
				)

	def _reverse_stock(self):
		batch_map = {}
		aggregated = []
		for item in self.items:
			if item.stock_entry_item:
				child = frappe.get_doc("Stock Entry Items", item.stock_entry_item)
				batch_map.setdefault(child.parent, []).append((child.name, item.quantity or 0))
			else:
				aggregated.append(item)

		for batch_name, entries in batch_map.items():
			batch = frappe.get_doc("Stock Entries", batch_name)
			updated = False
			from_customs = batch.status == "At Customs"
			for child_name, qty in entries:
				child = next((row for row in batch.items if row.name == child_name), None)
				if not child:
					continue
				child.issued_qty = max((child.issued_qty or 0) - qty, 0)
				child.reserved_qty = (child.reserved_qty or 0) + qty
				stock_ledger.reverse_issue(child, qty, from_customs=from_customs)
				updated = True
			if updated:
				batch.save(ignore_permissions=True)

		if aggregated:
			location_type, warehouse = self._source_location()
			reference = self._ledger_reference(location_type, warehouse)
			for item in aggregated:
				qty = flt(item.quantity or 0)
				if qty <= 0 or not item.product:
					continue
				stock_ledger.apply_delta(
					item.product,
					location_type,
					reference,
					reserved_delta=qty,
					issued_delta=-qty,
					warehouse=warehouse if location_type == "Warehouse" else None,
					remarks=f"Issue reversed for Delivery Note {self.name}",
				)

	@staticmethod
	def _ledger_reference(location_type: str, warehouse: str | None = None) -> str:
		return f"{location_type}::{warehouse or 'GLOBAL'}"

	def _source_location(self) -> tuple[str, str | None]:
		if hasattr(self, "_cached_source_location"):
			return self._cached_source_location
		delivery_source = frappe.db.get_value("Sales Order", self.sales_order, "delivery_source") if self.sales_order else None
		location_type = "Customs" if delivery_source == "Direct from Customs" else "Warehouse"
		warehouse = None
		for item in self.items:
			if item.warehouse:
				warehouse = item.warehouse
				break
		if not warehouse and self.sales_order:
			warehouse = frappe.db.get_value(
				"Sales Order Item",
				{"parent": self.sales_order, "warehouse": ["is", "set"]},
				"warehouse",
			)
		self._cached_source_location = (location_type, warehouse)
		return self._cached_source_location
