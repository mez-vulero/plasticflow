import frappe
from frappe.model.document import Document
from frappe.utils import nowdate

from plasticflow.stock import ledger as stock_ledger


class SalesOrder(Document):
	"""Coordinates the commercial process from order capture to delivery."""

	def validate(self):
		self._set_item_defaults()
		self._calculate_totals()
		self._ensure_status_alignment()

	def before_submit(self):
		reservations = self._collect_batch_reservations()
		self._validate_stock_availability(reservations)
		if self.delivery_source == "Warehouse":
			self._enforce_fifo(reservations)
		self.status = "Held" if self.delivery_source == "Direct from Customs" else "Payment Pending"
		if self.payment_status in {"Draft", "Payment Pending"}:
			self.payment_status = "Payment Pending"

	def on_submit(self):
		reservations = self._collect_batch_reservations()
		self._apply_reservations(reservations)
		self.db_set("status", self.status)
		self.db_set("payment_status", self.payment_status)

	def on_update_after_submit(self):
		if self.payment_status == "Payment Verified" and not self.invoice:
			invoice = self._create_invoice_draft()
			self.db_set("invoice", invoice.name)
			self.db_set("status", "Held" if self.delivery_source == "Direct from Customs" else "Invoiced")

	def on_cancel(self):
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
				if self.delivery_source in {"Warehouse", "Direct from Customs"}:
					frappe.throw(f"Stock allocation is required for product {item.product}.")
				continue
			child = frappe.get_doc("Plasticflow Stock Entry Item", item.batch_item)
			parent = frappe.get_doc("Plasticflow Stock Entry", child.parent)
			entry = reservations.setdefault(
				child.parent,
				{"rows": [], "from_customs": parent.status == "At Customs"},
			)
			entry["from_customs"] = parent.status == "At Customs"
			entry["rows"].append(
				{
					"child_name": child.name,
					"qty": item.quantity or 0,
				}
			)
		return reservations

	def _validate_stock_availability(self, reservations):
		for batch_name, payload in reservations.items():
			batch = frappe.get_doc("Plasticflow Stock Entry", batch_name)
			for entry in payload["rows"]:
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
		for batch_name, payload in reservations.items():
			batch = frappe.get_doc("Plasticflow Stock Entry", batch_name)
			updated = False
			for entry in payload["rows"]:
				child = next((row for row in batch.items if row.name == entry["child_name"]), None)
				if not child:
					continue
				child.reserved_qty = (child.reserved_qty or 0) + (entry["qty"] or 0)
				updated = True
				stock_ledger.adjust_for_reservation(child, entry["qty"], from_customs=payload["from_customs"])
			if updated:
				batch.save(ignore_permissions=True)

	def _release_reservations(self, reservations):
		for batch_name, payload in reservations.items():
			batch = frappe.get_doc("Plasticflow Stock Entry", batch_name)
			updated = False
			for entry in payload["rows"]:
				child = next((row for row in batch.items if row.name == entry["child_name"]), None)
				if not child:
					continue
				child.reserved_qty = max((child.reserved_qty or 0) - (entry["qty"] or 0), 0)
				updated = True
				stock_ledger.release_reservation(child, entry["qty"], from_customs=payload["from_customs"])
			if updated:
				batch.save(ignore_permissions=True)

	def _enforce_fifo(self, reservations):
		for batch_name, payload in reservations.items():
			if payload["from_customs"]:
				continue
			batch = frappe.get_doc("Plasticflow Stock Entry", batch_name)
			for entry in payload["rows"]:
				child = next((row for row in batch.items if row.name == entry["child_name"]), None)
				if not child:
					continue
				arrival_marker = batch.arrival_date or batch.creation
				available_older = frappe.db.sql(
					"""
					select sei.name
					from `tabPlasticflow Stock Entry Item` sei
					inner join `tabPlasticflow Stock Entry` se on se.name = sei.parent
					where se.warehouse = %s
					and sei.product = %s
					and se.status = 'Available'
					and (
						coalesce(se.arrival_date, se.creation) < %s
						or (
							coalesce(se.arrival_date, se.creation) = %s
							and se.creation < %s
						)
					)
					and (sei.received_qty - sei.reserved_qty - sei.issued_qty) > 0
					limit 1
					""",
					(batch.warehouse, child.product, arrival_marker, arrival_marker, batch.creation),
				)
				if available_older:
					frappe.throw(
						f"FIFO policy violation for {child.product}. Older stock is available in warehouse {batch.warehouse}.",
					)

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
