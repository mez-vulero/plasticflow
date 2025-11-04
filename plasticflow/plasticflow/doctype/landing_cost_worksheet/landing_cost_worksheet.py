import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime
from plasticflow.stock import ledger as stock_ledger


class LandingCostWorksheet(Document):
	"""Aggregates shipment logistics costs and allocates landed cost per item."""

	def validate(self):
		self._ensure_shipment_context()
		self._calculate_totals()
		self._build_allocations()
		self._update_status_flag()

	def on_submit(self):
		self._lock_shipment_costs()

	def on_cancel(self):
		self._revert_shipment_lock()

	# -------------------------------------------------------------------------
	# Internal helpers

	def _ensure_shipment_context(self):
		if not self.import_shipment:
			self.total_base_amount = 0
			self.total_base_amount_import = 0
			self.total_quantity = 0
			return
		if not frappe.db.exists("Import Shipment", self.import_shipment):
			frappe.throw("Import Shipment does not exist.")

		shipment = frappe.get_doc("Import Shipment", self.import_shipment)
		if shipment.purchase_order:
			self.purchase_order = self.purchase_order or shipment.purchase_order

		# Derive currencies
		if not self.currency:
			self.currency = shipment.get("local_currency") or frappe.db.get_default("currency") or shipment.currency
		self.shipment_currency = shipment.currency

		# Exchange rate from shipment currency (usually foreign) to worksheet currency
		if not self.shipment_exchange_rate and shipment.get("purchase_order"):
			po_rate = frappe.db.get_value("Purchase Order", shipment.purchase_order, "purchase_exchange_rate")
			if po_rate:
				self.shipment_exchange_rate = flt(po_rate)
		if self.shipment_currency == self.currency and not self.shipment_exchange_rate:
			self.shipment_exchange_rate = 1
		self.shipment_exchange_rate = flt(self.shipment_exchange_rate or 0)

		self.total_quantity = shipment.total_quantity or sum(flt(item.quantity or 0) for item in shipment.items)
		self.total_base_amount_import = sum(flt(item.base_amount or 0) for item in shipment.items)
		self.total_base_amount = self._convert_to_local(self.total_base_amount_import)

	def _calculate_totals(self):
		total_additional_local = 0.0
		total_additional_import = 0.0

		for row in self.cost_components:
			row.currency = row.currency or self.currency
			row.exchange_rate = self._normalise_component_rate(row)
			converted = flt(row.amount or 0) * flt(row.exchange_rate or 0)
			row.converted_amount = converted

			total_additional_local += converted
			total_additional_import += self._convert_to_import(converted)

		self.total_additional_cost = total_additional_local
		self.total_additional_cost_import = total_additional_import

		self.total_landed_cost = flt(self.total_base_amount) + flt(self.total_additional_cost)
		self.total_landed_cost_import = (
			flt(self.total_base_amount_import) + flt(self.total_additional_cost_import)
		)

		self.avg_landed_cost = (
			self.total_landed_cost / flt(self.total_quantity) if flt(self.total_quantity) else 0
		)
		self.avg_landed_cost_import = (
			self.total_landed_cost_import / flt(self.total_quantity) if flt(self.total_quantity) else 0
		)

	def _build_allocations(self):
		if not self.import_shipment:
			self.allocations = []
			return

		shipment = frappe.get_doc("Import Shipment", self.import_shipment)
		allocation_basis = self._get_allocation_basis(shipment)
		total_basis = sum(allocation_basis.values())
		additional_total_local = flt(self.total_additional_cost)
		additional_total_import = flt(self.total_additional_cost_import)

		self.set("allocations", [])

		for item in shipment.items:
			basis_value = allocation_basis.get(item.name, 0)
			allocation_ratio = basis_value / total_basis if total_basis else 0
			quantity = flt(item.quantity or 0)

			base_amount_import = flt(item.base_amount or 0)
			base_amount_local = flt(item.base_amount_local or 0)
			if not base_amount_local:
				base_amount_local = self._convert_to_local(base_amount_import)

			additional_cost_local = additional_total_local * allocation_ratio
			additional_cost_import = additional_total_import * allocation_ratio

			landed_cost_local = base_amount_local + additional_cost_local
			landed_cost_import = base_amount_import + additional_cost_import

			landed_rate_local = landed_cost_local / quantity if quantity else 0
			landed_rate_import = landed_cost_import / quantity if quantity else 0

			self.append(
				"allocations",
				{
					"shipment_item": item.name,
					"product": item.product,
					"quantity": quantity,
					"base_amount": base_amount_local,
					"base_amount_import": base_amount_import,
					"allocation_ratio": allocation_ratio * 100,
					"additional_cost": additional_cost_local,
					"additional_cost_import": additional_cost_import,
					"landed_cost_amount": landed_cost_local,
					"landed_cost_amount_import": landed_cost_import,
					"landed_cost_rate": landed_rate_local,
					"landed_cost_rate_import": landed_rate_import,
				},
			)

	def _get_allocation_basis(self, shipment):
		method = (self.allocation_method or "By Value").lower()
		basis = {}
		for item in shipment.items:
			if method == "by quantity":
				value = flt(item.quantity or 0)
			else:
				base_amount = flt(item.base_amount or 0)
				if not base_amount and item.quantity:
					base_amount = flt(item.quantity) * flt(item.base_rate or 0)
				value = base_amount
			basis[item.name] = max(value, 0)
		return basis

	def _update_status_flag(self):
		if self.docstatus == 0:
			self.status = "Draft" if not self.is_local_allocated else "In Review"
		elif self.docstatus == 1:
			self.status = "Locked"

	@property
	def is_local_allocated(self):
		return bool(self.allocations)

	def _lock_shipment_costs(self):
		if not self.import_shipment:
			return

		shipment = frappe.get_doc("Import Shipment", self.import_shipment)
		item_map = {row.shipment_item: row for row in self.allocations}

		for item in shipment.items:
			allocation = item_map.get(item.name)
			if not allocation:
				continue

			item.base_amount_local = self._convert_to_local(flt(item.base_amount or 0))
			item.landed_cost_amount = allocation.landed_cost_amount_import
			item.landed_cost_amount_local = allocation.landed_cost_amount
			item.landed_cost_rate = allocation.landed_cost_rate_import
			item.landed_cost_rate_local = allocation.landed_cost_rate
			item.allocation_ratio = allocation.allocation_ratio

		shipment.local_currency = self.currency
		shipment.total_landed_cost = self.total_landed_cost_import
		shipment.per_unit_landed_cost = self.avg_landed_cost_import
		shipment.total_landed_cost_local = self.total_landed_cost
		shipment.per_unit_landed_cost_local = self.avg_landed_cost
		shipment.landing_cost_status = "Locked"
		shipment.landing_cost_note = f"Landed cost locked via {self.name}"
		shipment.save(ignore_permissions=True)

		self._update_purchase_order_receipts(shipment)

		# Update downstream stock entry items
		for item in shipment.items:
			stock_entry_items = frappe.db.get_all(
				"Stock Entry Items",
				filters={"import_shipment_item": item.name},
				pluck="name",
			)
			for sei in stock_entry_items:
				frappe.db.set_value(
					"Stock Entry Items",
					sei,
					{
						"landed_cost_rate": item.landed_cost_rate,
						"landed_cost_amount": item.landed_cost_amount,
						"landed_cost_rate_local": item.landed_cost_rate_local,
						"landed_cost_amount_local": item.landed_cost_amount_local,
					},
					update_modified=False,
				)

		stock_entries = frappe.db.get_all(
			"Stock Entries",
			filters={"import_shipment": shipment.name, "docstatus": 1},
			pluck="name",
		)
		for name in stock_entries:
			batch_doc = frappe.get_doc("Stock Entries", name)
			stock_ledger.update_stock_entry_balances(batch_doc)

		self.locked_on = now_datetime()
		self.lock_note = f"Locked via worksheet {self.name}"

	def _revert_shipment_lock(self):
		if not self.import_shipment:
			return
		shipment = frappe.get_doc("Import Shipment", self.import_shipment)
		if shipment.landing_cost_status != "Locked":
			return

		for item in shipment.items:
			item.landed_cost_amount = 0
			item.landed_cost_amount_local = 0
			item.landed_cost_rate = 0
			item.landed_cost_rate_local = 0
			item.allocation_ratio = 0

		shipment.total_landed_cost = 0
		shipment.total_landed_cost_local = 0
		shipment.per_unit_landed_cost = 0
		shipment.per_unit_landed_cost_local = 0
		shipment.landing_cost_status = "Draft"
		shipment.landing_cost_note = None
		shipment.save(ignore_permissions=True)

		self._revert_purchase_order_receipts(shipment)

		stock_entries = frappe.db.get_all(
			"Stock Entries",
			filters={"import_shipment": shipment.name, "docstatus": 1},
			pluck="name",
		)
		for name in stock_entries:
			batch_doc = frappe.get_doc("Stock Entries", name)
			for row in batch_doc.items:
				row.landed_cost_rate = 0
				row.landed_cost_amount = 0
				row.landed_cost_rate_local = 0
				row.landed_cost_amount_local = 0
			batch_doc.save(ignore_permissions=True)
			stock_ledger.update_stock_entry_balances(batch_doc)

	# -------------------------------------------------------------------------
	# Utilities

	def _update_purchase_order_receipts(self, shipment):
		if not shipment.purchase_order:
			return

		updated = False
		for item in shipment.items:
			if not item.purchase_order_item:
				continue
			po_row = frappe.db.get_value(
				"Purchase Order Item",
				item.purchase_order_item,
				["received_qty", "quantity"],
				as_dict=True,
			)
			if not po_row:
				continue
			current = flt(po_row.received_qty or 0)
			ordered = flt(po_row.quantity or 0)
			new_qty = current + flt(item.quantity or 0)
			if ordered and new_qty > ordered:
				new_qty = ordered
			frappe.db.set_value(
				"Purchase Order Item",
				item.purchase_order_item,
				{
					"received_qty": new_qty,
					"import_shipment_item": item.name,
				},
				update_modified=False,
			)
			updated = True

		if updated:
			po = frappe.get_doc("Purchase Order", shipment.purchase_order)
			po.reload()
			po.update_receipt_status()


def get_dashboard_data():
	return {
		"fieldname": "import_shipment",
		"transactions": [],
		"internal_links": {
			"Import Shipment": ["import_shipment"],
			"Purchase Order": ["purchase_order"],
		},
	}

	def _revert_purchase_order_receipts(self, shipment):
		if not shipment.purchase_order:
			return

		updated = False
		for item in shipment.items:
			if not item.purchase_order_item:
				continue
			po_row = frappe.db.get_value(
				"Purchase Order Item",
				item.purchase_order_item,
				"received_qty",
			)
			if po_row is None:
				continue
			current = flt(po_row or 0)
			new_qty = current - flt(item.quantity or 0)
			if new_qty < 0:
				new_qty = 0
			frappe.db.set_value(
				"Purchase Order Item",
				item.purchase_order_item,
				{
					"received_qty": new_qty,
					"import_shipment_item": None,
				},
				update_modified=False,
			)
			updated = True

		if updated:
			po = frappe.get_doc("Purchase Order", shipment.purchase_order)
			po.reload()
			po.update_receipt_status()

	def _normalise_component_rate(self, row) -> float:
		if row.currency == self.currency:
			return 1.0

		if row.currency == self.shipment_currency:
			if self.shipment_currency == self.currency:
				return 1.0
			if flt(self.shipment_exchange_rate) <= 0:
				frappe.throw("Set Exchange Rate (Shipment → Worksheet) before converting shipment cost components.")
			return flt(self.shipment_exchange_rate)

		exchange_rate = flt(row.exchange_rate or 0)
		if exchange_rate <= 0:
			frappe.throw(
				f"Provide an exchange rate for cost component '{row.cost_type}' ({row.currency} → {self.currency})."
			)
		return exchange_rate

	def _convert_to_local(self, amount: float) -> float:
		if self.shipment_currency == self.currency:
			return flt(amount)
		rate = flt(self.shipment_exchange_rate or 0)
		if rate <= 0:
			if abs(amount) > 0.0001:
				frappe.throw("Set Exchange Rate (Shipment → Worksheet) to convert values into the worksheet currency.")
			return 0
		return flt(amount) * rate

	def _convert_to_import(self, local_amount: float) -> float:
		if self.shipment_currency == self.currency:
			return flt(local_amount)
		rate = flt(self.shipment_exchange_rate or 0)
		if rate <= 0:
			return 0.0
		return flt(local_amount) / rate
