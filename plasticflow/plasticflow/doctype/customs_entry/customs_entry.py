import frappe
from frappe.model.document import Document
from frappe.utils import nowdate

from plasticflow.stock import ledger as stock_ledger


class CustomsEntry(Document):
	"""Captures inbound customs clearance details for imported stock."""

	def validate(self):
		self._sync_from_import_shipment()
		self._set_item_defaults()
		self._update_totals()

	def before_save(self):
		if self.docstatus != 1:
			return
		previous = self.get_doc_before_save()
		if not previous:
			return
		allowed = {"clearance_status"}
		changed = []
		for field in self.meta.get_valid_columns():
			if field in allowed:
				continue
			if previous.get(field) != self.get(field):
				changed.append(field)
		if frappe.as_json(previous.items) != frappe.as_json(self.items):
			changed.append("items")
		if changed:
			frappe.throw("Only Clearance Status can be updated after submission.")

	def on_submit(self):
		if self.clearance_status != "Cleared":
			frappe.throw("Customs Entry cannot be submitted until status is set to Cleared.")
		self._create_plasticflow_stock_entry()
		stock_ledger.sync_customs_entry(self, plasticflow_stock_entry=self.plasticflow_stock_entry)

	def on_update_after_submit(self):
		if self.clearance_status == "At Warehouse" and self.plasticflow_stock_entry:
			self._transfer_to_warehouse()
		elif self.clearance_status == "Cleared":
			stock_ledger.sync_customs_entry(self, plasticflow_stock_entry=self.plasticflow_stock_entry)

	def on_cancel(self):
		stock_ledger.clear_customs_entry(self)
		if self.plasticflow_stock_entry:
			plasticflow_stock_entry = frappe.get_doc("Plasticflow Stock Entry", self.plasticflow_stock_entry)
			if plasticflow_stock_entry.docstatus == 1:
				plasticflow_stock_entry.cancel()
			if frappe.db.exists("Plasticflow Stock Entry", plasticflow_stock_entry.name):
				frappe.db.set_value(
					"Plasticflow Stock Entry",
					plasticflow_stock_entry.name,
					"customs_entry",
					None,
					update_modified=False,
				)
		if frappe.db.exists("Customs Entry", self.name):
			frappe.db.set_value("Customs Entry", self.name, "plasticflow_stock_entry", None, update_modified=False)
		self.plasticflow_stock_entry = None

	def _set_item_defaults(self):
		for item in self.items:
			if item.product and not item.product_name:
				item.product_name = frappe.db.get_value("Product", item.product, "product_name")
			if item.product and not item.uom:
				item.uom = frappe.db.get_value("Product", item.product, "uom")
			if self.import_shipment and not item.import_shipment_item and item.product:
				shipment_item = frappe.db.get_value(
					"Import Shipment Item",
					{"parent": self.import_shipment, "product": item.product},
					"name",
				)
				if shipment_item:
					item.import_shipment_item = shipment_item

	def _update_totals(self):
		total_qty = 0
		for item in self.items:
			total_qty += item.quantity or 0

		self.total_quantity = total_qty
		self.total_weight = 0
		self.total_declared_value = 0

	def _sync_from_import_shipment(self):
		if not self.import_shipment or not frappe.db.exists("Import Shipment", self.import_shipment):
			return

		shipment = frappe.get_doc("Import Shipment", self.import_shipment)
		if not self.shipment_reference:
			self.shipment_reference = shipment.import_reference
		if shipment.supplier and not self.supplier:
			self.supplier = shipment.supplier
		if shipment.incoterm:
			self.incoterm = shipment.incoterm
		if shipment.expected_arrival and not self.arrival_date:
			self.arrival_date = shipment.expected_arrival
		if shipment.total_shipment_amount and not self.total_declared_value:
			self.total_declared_value = shipment.total_shipment_amount

		if not self.items:
			for item in shipment.items:
				self.append(
					"items",
					{
						"product": item.product,
						"product_name": item.product_name,
						"description": item.description,
						"quantity": item.quantity,
						"uom": item.uom,
						"import_shipment_item": item.name,
					},
				)

	def _create_plasticflow_stock_entry(self):
		if self.plasticflow_stock_entry:
			return

		if not self.destination_warehouse:
			default_wh = self._guess_destination_warehouse()
			if not default_wh:
				frappe.throw("Destination Warehouse is required to create Plasticflow Stock Entry.")
			self.destination_warehouse = default_wh

		batch = frappe.new_doc("Plasticflow Stock Entry")
		batch.customs_entry = self.name
		batch.import_shipment = self.import_shipment
		batch.arrival_date = nowdate()
		batch.warehouse = self.destination_warehouse
		batch.status = "At Customs"

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
		self.db_set("plasticflow_stock_entry", batch.name)
		self.plasticflow_stock_entry = batch.name

	def _guess_destination_warehouse(self):
		warehouses = {item.product: frappe.db.get_value("Product", item.product, "default_warehouse") for item in self.items if item.product}
		candidates = {wh for wh in warehouses.values() if wh}
		if len(candidates) == 1:
			return candidates.pop()
		return None

	def _transfer_to_warehouse(self):
		source_entry = frappe.get_doc("Plasticflow Stock Entry", self.plasticflow_stock_entry)
		if source_entry.status == "Available" and source_entry.warehouse:
			return

		previous_status = source_entry.status
		if self.destination_warehouse and not source_entry.warehouse:
			source_entry.warehouse = self.destination_warehouse
		source_entry.status = "Available"
		source_entry.arrival_date = nowdate()
		source_entry.save(ignore_permissions=True)

		if previous_status == "At Customs":
			stock_ledger.transfer_customs_to_warehouse(self, source_entry)
