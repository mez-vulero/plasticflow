import frappe
from frappe.model.document import Document
from frappe.utils import nowdate


class SalesOrder(Document):
	"""Coordinates the commercial process from order capture to delivery."""

	def validate(self):
		self._set_item_defaults()
		self._calculate_totals()
		self._ensure_status_alignment()

	def before_submit(self):
		if self.delivery_source == "Warehouse":
			reservations = self._collect_batch_reservations()
			self._validate_stock_availability(reservations)
		self.status = "Payment Pending"
		if self.payment_status in {"Draft", "Payment Pending"}:
			self.payment_status = "Payment Pending"

	def on_submit(self):
		if self.delivery_source == "Warehouse":
			reservations = self._collect_batch_reservations()
			self._apply_reservations(reservations)
		self.db_set("status", self.status)
		self.db_set("payment_status", self.payment_status)

	def on_update_after_submit(self):
		if self.payment_status == "Payment Verified" and not self.invoice:
			invoice = self._create_invoice_draft()
			self.db_set("invoice", invoice.name)
			self.db_set("status", "Invoiced")

	def on_cancel(self):
		if self.delivery_source == "Warehouse":
			reservations = self._collect_batch_reservations()
			self._release_reservations(reservations)
		self.db_set("status", "Cancelled")

	def _set_item_defaults(self):
		for item in self.items:
			if item.product and not item.product_name:
				item.product_name = frappe.db.get_value("Product", item.product, "product_name")
			if item.product and not item.uom:
				item.uom = frappe.db.get_value("Product", item.product, "uom")
			if item.quantity and item.rate:
				item.amount = (item.quantity or 0) * (item.rate or 0)

	def _calculate_totals(self):
		self.total_quantity = sum((item.quantity or 0) for item in self.items)
		self.total_amount = sum((item.amount or 0) for item in self.items)

	def _ensure_status_alignment(self):
		if self.payment_status == "Payment Verified" and self.status not in {"Invoiced", "Ready for Delivery", "Completed"}:
			self.status = "Payment Verified"

	def _collect_batch_reservations(self):
		reservations = {}
		for item in self.items:
			if not item.batch_item:
				if self.delivery_source == "Warehouse":
					frappe.throw(f"Batch allocation is required for product {item.product} when sourcing from Warehouse.")
				continue
			child = frappe.get_doc("Stock Batch Item", item.batch_item)
			reservations.setdefault(child.parent, []).append(
				{
					"child_name": child.name,
					"qty": item.quantity or 0,
				}
			)
		return reservations

	def _validate_stock_availability(self, reservations):
		for batch_name, entries in reservations.items():
			batch = frappe.get_doc("Stock Batch", batch_name)
			for entry in entries:
				child = next((row for row in batch.items if row.name == entry["child_name"]), None)
				if not child:
					frappe.throw("Unable to locate batch item for reservation.")
				available = (child.received_qty or 0) - (child.reserved_qty or 0) - (child.issued_qty or 0)
				if entry["qty"] > available:
					frappe.throw(
						f"Not enough available quantity in batch {batch.name} for {child.product}. "
						f"Requested {entry['qty']}, available {available}."
					)

	def _apply_reservations(self, reservations):
		for batch_name, entries in reservations.items():
			batch = frappe.get_doc("Stock Batch", batch_name)
			updated = False
			for entry in entries:
				child = next((row for row in batch.items if row.name == entry["child_name"]), None)
				if not child:
					continue
				child.reserved_qty = (child.reserved_qty or 0) + (entry["qty"] or 0)
				updated = True
			if updated:
				batch.save(ignore_permissions=True)

	def _release_reservations(self, reservations):
		for batch_name, entries in reservations.items():
			batch = frappe.get_doc("Stock Batch", batch_name)
			updated = False
			for entry in entries:
				child = next((row for row in batch.items if row.name == entry["child_name"]), None)
				if not child:
					continue
				child.reserved_qty = max((child.reserved_qty or 0) - (entry["qty"] or 0), 0)
				updated = True
			if updated:
				batch.save(ignore_permissions=True)

	def _create_invoice_draft(self):
		invoice = frappe.new_doc("Plasticflow Invoice")
		invoice.sales_order = self.name
		invoice.customer = self.customer
		invoice.currency = self.currency
		invoice.invoice_date = nowdate()
		invoice.total_amount = self.total_amount
		for item in self.items:
			invoice.append(
				"items",
				{
					"product": item.product,
					"product_name": item.product_name,
					"description": item.description,
					"quantity": item.quantity,
					"uom": item.uom,
					"rate": item.rate,
					"amount": item.amount,
				},
			)
		invoice.insert(ignore_permissions=True)
		return invoice
