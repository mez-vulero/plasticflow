import frappe
from frappe.model.document import Document
from frappe.utils import nowdate

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
		frappe.db.set_value("Sales Order", self.sales_order, "status", "Ready for Delivery")
		frappe.db.set_value("Gate Pass", self.gate_pass, "status", "Issued")

	def _set_item_defaults(self):
		for item in self.items:
			if item.product and not item.product_name:
				item.product_name = frappe.db.get_value("Product", item.product, "product_name")

	def _issue_stock(self):
		batch_map = {}
		for item in self.items:
			if not item.stock_entry_item:
				continue
			child = frappe.get_doc("Plasticflow Stock Entry Item", item.stock_entry_item)
			batch_map.setdefault(child.parent, []).append((child.name, item.quantity or 0))

		for batch_name, entries in batch_map.items():
			batch = frappe.get_doc("Plasticflow Stock Entry", batch_name)
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

	def _reverse_stock(self):
		batch_map = {}
		for item in self.items:
			if not item.stock_entry_item:
				continue
			child = frappe.get_doc("Plasticflow Stock Entry Item", item.stock_entry_item)
			batch_map.setdefault(child.parent, []).append((child.name, item.quantity or 0))

		for batch_name, entries in batch_map.items():
			batch = frappe.get_doc("Plasticflow Stock Entry", batch_name)
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
