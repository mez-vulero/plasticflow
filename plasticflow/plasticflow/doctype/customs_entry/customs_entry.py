import frappe
from frappe.model.document import Document


class CustomsEntry(Document):
	"""Captures inbound customs clearance details for imported stock."""

	def validate(self):
		self._set_item_defaults()
		self._update_totals()

	def on_submit(self):
		if self.clearance_status != "Cleared":
			frappe.throw("Customs Entry cannot be submitted until status is set to Cleared.")
		self._create_stock_batch()

	def _set_item_defaults(self):
		for item in self.items:
			if item.product and not item.product_name:
				item.product_name = frappe.db.get_value("Product", item.product, "product_name")
			if item.product and not item.uom:
				item.uom = frappe.db.get_value("Product", item.product, "uom")
			if item.quantity and item.rate:
				item.amount = (item.rate or 0) * (item.quantity or 0)

	def _update_totals(self):
		total_qty = 0
		total_weight = 0
		total_value = 0

		for item in self.items:
			total_qty += item.quantity or 0
			total_weight += item.weight_kg or 0
			if item.quantity and item.rate:
				item.amount = (item.rate or 0) * (item.quantity or 0)
			total_value += item.amount or 0

		self.total_quantity = total_qty
		self.total_weight = total_weight
		if total_value:
			self.total_declared_value = total_value

	def _create_stock_batch(self):
		if self.stock_batch:
			return

		if not self.destination_warehouse:
			default_wh = self._guess_destination_warehouse()
			if not default_wh:
				frappe.throw("Destination Warehouse is required to create Stock Batch.")
			self.destination_warehouse = default_wh

		batch = frappe.new_doc("Stock Batch")
		batch.customs_entry = self.name
		batch.arrival_date = self.cleared_on or self.arrival_date
		batch.warehouse = self.destination_warehouse
		batch.status = "Available"

		for item in self.items:
			batch.append(
				"items",
				{
					"product": item.product,
					"product_name": item.product_name,
					"quantity": item.quantity,
					"uom": item.uom,
					"received_qty": item.quantity,
					"reserved_qty": 0,
					"issued_qty": 0,
					"warehouse_location": item.warehouse_location,
					"customs_entry_item": item.name,
				},
			)

		batch.insert(ignore_permissions=True)
		batch.submit()
		self.db_set("stock_batch", batch.name)

	def _guess_destination_warehouse(self):
		warehouses = {item.product: frappe.db.get_value("Product", item.product, "default_warehouse") for item in self.items if item.product}
		candidates = {wh for wh in warehouses.values() if wh}
		if len(candidates) == 1:
			return candidates.pop()
		return None
