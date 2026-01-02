import frappe
from frappe.model.document import Document
from frappe.utils import flt, nowdate

from plasticflow.stock import ledger as stock_ledger
from plasticflow.stock import uom as stock_uom


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
		self._update_sales_order_status()

	def on_update_after_submit(self):
		if self.status == "Delivered":
			self._update_sales_order_status()

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

	def _get_product_uom(self, product: str | None) -> str | None:
		if not product:
			return None
		cache = getattr(self, "_product_uom_cache", None)
		if cache is None:
			cache = {}
			self._product_uom_cache = cache
		if product not in cache:
			cache[product] = frappe.db.get_value("Product", product, "uom")
		return cache[product]

	def _get_sales_order_uom(self, product: str | None) -> str | None:
		if not self.sales_order or not product:
			return None
		cache = getattr(self, "_so_uom_cache", None)
		if cache is None:
			cache = {}
			self._so_uom_cache = cache
		if product not in cache:
			cache[product] = frappe.db.get_value(
				"Sales Order Item",
				{"parent": self.sales_order, "product": product},
				"uom",
			)
		return cache[product]

	def _resolve_sales_uom(self, item, fallback: str | None = None) -> str | None:
		if item.uom:
			return item.uom
		so_uom = self._get_sales_order_uom(item.product)
		return so_uom or fallback

	def _to_stock_qty(self, item, quantity: float, stock_uom_name: str | None = None) -> float:
		stock_uom_name = stock_uom_name or self._get_product_uom(item.product)
		sales_uom_name = self._resolve_sales_uom(item, stock_uom_name)
		return stock_uom.convert_quantity(quantity, sales_uom_name, stock_uom_name)

	def _set_item_defaults(self):
		for item in self.items:
			if item.product and not item.product_name:
				item.product_name = frappe.db.get_value("Product", item.product, "product_name")
			if item.product and not item.uom:
				item.uom = self._get_sales_order_uom(item.product)

	def _issue_stock(self):
		batch_map = {}
		aggregated = []
		for item in self.items:
			if item.stock_entry_item:
				child = frappe.get_doc("Stock Entry Items", item.stock_entry_item)
				batch_map.setdefault(child.parent, []).append((child.name, item))
			else:
				aggregated.append(item)

		for batch_name, entries in batch_map.items():
			batch = frappe.get_doc("Stock Entries", batch_name)
			updated = False
			from_customs = batch.status == "At Customs"
			for child_name, item in entries:
				child = next((row for row in batch.items if row.name == child_name), None)
				if not child:
					continue
				quantity = flt(item.quantity or 0)
				stock_uom_name = child.uom or self._get_product_uom(child.product)
				qty_stock = self._to_stock_qty(item, quantity, stock_uom_name)
				child.reserved_qty = max((child.reserved_qty or 0) - qty_stock, 0)
				child.issued_qty = (child.issued_qty or 0) + qty_stock
				stock_ledger.issue_stock(child, qty_stock, from_customs=from_customs)
				updated = True
			if updated:
				batch.save(ignore_permissions=True)

		if aggregated:
			location_type, warehouse = self._source_location()
			reference = self._ledger_reference(location_type, warehouse)
			for item in aggregated:
				qty = flt(item.quantity or 0)
				qty_stock = self._to_stock_qty(item, qty)
				if qty_stock <= 0 or not item.product:
					continue
				stock_ledger.apply_delta(
					item.product,
					location_type,
					reference,
					reserved_delta=-qty_stock,
					issued_delta=qty_stock,
					warehouse=warehouse if location_type == "Warehouse" else None,
					remarks=f"Issued via Delivery Note {self.name}",
				)

	def _reverse_stock(self):
		batch_map = {}
		aggregated = []
		for item in self.items:
			if item.stock_entry_item:
				child = frappe.get_doc("Stock Entry Items", item.stock_entry_item)
				batch_map.setdefault(child.parent, []).append((child.name, item))
			else:
				aggregated.append(item)

		for batch_name, entries in batch_map.items():
			batch = frappe.get_doc("Stock Entries", batch_name)
			updated = False
			from_customs = batch.status == "At Customs"
			for child_name, item in entries:
				child = next((row for row in batch.items if row.name == child_name), None)
				if not child:
					continue
				quantity = flt(item.quantity or 0)
				stock_uom_name = child.uom or self._get_product_uom(child.product)
				qty_stock = self._to_stock_qty(item, quantity, stock_uom_name)
				child.issued_qty = max((child.issued_qty or 0) - qty_stock, 0)
				child.reserved_qty = (child.reserved_qty or 0) + qty_stock
				stock_ledger.reverse_issue(child, qty_stock, from_customs=from_customs)
				updated = True
			if updated:
				batch.save(ignore_permissions=True)

		if aggregated:
			location_type, warehouse = self._source_location()
			reference = self._ledger_reference(location_type, warehouse)
			for item in aggregated:
				qty = flt(item.quantity or 0)
				qty_stock = self._to_stock_qty(item, qty)
				if qty_stock <= 0 or not item.product:
					continue
				stock_ledger.apply_delta(
					item.product,
					location_type,
					reference,
					reserved_delta=qty_stock,
					issued_delta=-qty_stock,
					warehouse=warehouse if location_type == "Warehouse" else None,
					remarks=f"Issue reversed for Delivery Note {self.name}",
				)

	def _update_sales_order_status(self):
		if not self.sales_order or not frappe.db.exists("Sales Order", self.sales_order):
			return
		so = frappe.get_doc("Sales Order", self.sales_order)
		target_status = so.status
		if so.gate_pass and frappe.db.exists("Gate Pass Request", so.gate_pass):
			gp_status = frappe.db.get_value("Gate Pass Request", so.gate_pass, "status")
			if gp_status == "Dispatched":
				target_status = "Completed"
		if target_status != so.status:
			so.db_set("status", target_status, update_modified=False)

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
