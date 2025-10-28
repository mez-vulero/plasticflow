import frappe
from frappe.model.document import Document
from frappe.utils import nowdate


class PlasticflowStockEntry(Document):
	"""Represents stock entry tracking movement between customs and warehouses."""

	def validate(self):
		self._populate_from_customs_entry()
		self._update_item_balances()
		self._update_totals()
		self._set_status()

	def before_insert(self):
		self._populate_from_customs_entry()

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

	def _populate_from_customs_entry(self):
		if not self.customs_entry or not frappe.db.exists("Customs Entry", self.customs_entry):
			return

		customs_entry = frappe.get_doc("Customs Entry", self.customs_entry)

		if not self.arrival_date:
			self.arrival_date = nowdate()

		if customs_entry.destination_warehouse and not self.warehouse:
			self.warehouse = customs_entry.destination_warehouse

		if not self.items:
			for item in customs_entry.items:
				self.append(
					"items",
					{
						"product": item.product,
						"product_name": item.product_name,
						"received_qty": item.quantity,
						"reserved_qty": 0,
						"issued_qty": 0,
						"uom": item.uom,
						"warehouse_location": item.get("warehouse_location"),
						"customs_entry_item": item.name,
					},
				)

		if not self.status:
			self.status = "Available" if customs_entry.clearance_status == "At Warehouse" else "At Customs"
