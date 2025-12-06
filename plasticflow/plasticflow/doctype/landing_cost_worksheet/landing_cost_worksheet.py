from collections import defaultdict

import json
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime

from plasticflow.stock import ledger as stock_ledger

TAX_PERCENT_BY_TYPE = {
	"import duty tax 5%": 5.0,
	"excise tax 3%": 3.0,
	"sur tax 10%": 10.0,
	"social welfare tax 3%": 3.0,
	"withholding tax 3%": 3.0,
	"vat 15%": 15.0,
}


class LandingCostWorksheet(Document):
	"""Aggregates shipment logistics costs and allocates landed cost per item."""

	def validate(self):
		self._ensure_single_shipment_constraint()
		self._ensure_shipment_context()
		self._calculate_totals()
		self._build_allocations()
		self._build_product_summary()
		self._update_status_flag()
		if self.docstatus == 0:
			self._sync_shipment_allocations()
			self.flags.shipment_synced_in_validate = True

	def on_submit(self):
		self._lock_shipment_costs()

	def on_cancel(self):
		self._revert_shipment_lock()

	def on_update(self):
		if self.docstatus != 0:
			return
		if getattr(self.flags, "shipment_synced_in_validate", False):
			return
		self._sync_shipment_allocations()

	# -------------------------------------------------------------------------
	# Internal helpers

	def _ensure_single_shipment_constraint(self):
		if not self.import_shipment:
			return

		existing = frappe.db.get_value(
			"Landing Cost Worksheet",
			{
				"import_shipment": self.import_shipment,
				"name": ["!=", self.name],
				"docstatus": ["!=", 2],
			},
			"name",
		)

		if existing:
			frappe.throw(
				_("Landing Cost Worksheet {0} already exists for Import Shipment {1}.").format(
					existing, self.import_shipment
				)
			)

	def _ensure_shipment_context(self):
		if not self.import_shipment:
			self.total_base_amount = 0
			self.total_base_amount_import = 0
			self.total_quantity = 0
			self.shipment_quantity_tons = 0
			self.shipment_amount_import = 0
			self.supplier = None
			self.country_of_origin = None
			self.port_of_loading = None
			self.port_of_discharge = None
			return
		if not frappe.db.exists("Import Shipment", self.import_shipment):
			frappe.throw("Import Shipment does not exist.")

		shipment = frappe.get_doc("Import Shipment", self.import_shipment)
		self._shipment_doc = shipment
		if shipment.purchase_order:
			self.purchase_order = self.purchase_order or shipment.purchase_order
		self.supplier = shipment.get("supplier")
		self.country_of_origin = shipment.get("country_of_origin")
		self.port_of_loading = shipment.get("port_of_loading")
		self.port_of_discharge = shipment.get("port_of_discharge")
		self.shipment_amount_import = shipment.get("total_shipment_amount")

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
		self.shipment_quantity_tons = self.total_quantity
		self.total_base_amount_import = sum(flt(item.base_amount or 0) for item in shipment.items)
		self.total_base_amount = self._convert_to_local(self.total_base_amount_import)

	def _calculate_totals(self):
		if not self.import_shipment:
			self.total_additional_cost = 0
			self.total_additional_cost_import = 0
			self.tax_cost_total = 0
			self.tax_cost_total_import = 0
			self.total_landed_cost = flt(self.total_base_amount)
			self.total_landed_cost_import = flt(self.total_base_amount_import)
			self.avg_landed_cost = 0
			self.avg_landed_cost_import = 0
			self.foreign_cost_total = 0
			self.local_cost_total = 0
			self._component_breakdown = {"items": {}, "totals": {"local": defaultdict(float), "import": defaultdict(float)}}
			return

		shipment = getattr(self, "_shipment_doc", None) or frappe.get_doc("Import Shipment", self.import_shipment)
		self._shipment_doc = shipment

		total_additional_local = 0.0
		total_additional_import = 0.0

		breakdown = self._allocate_cost_components(shipment)
		self._component_breakdown = breakdown

		local_totals = breakdown["totals"]["local"]
		import_totals = breakdown["totals"]["import"]

		foreign_total_local = flt(local_totals["foreign"])
		foreign_total_import = flt(import_totals["foreign"])

		self.foreign_cost_total = foreign_total_import
		self.local_cost_total = flt(local_totals["local"])
		self.tax_cost_total = flt(local_totals["tax"])
		self.tax_cost_total_import = flt(import_totals["tax"])

		total_additional_local = foreign_total_local + self.local_cost_total
		total_additional_import = foreign_total_import + import_totals["local"]

		self.total_additional_cost = total_additional_local
		self.total_additional_cost_import = total_additional_import

		self.total_landed_cost = flt(self.total_base_amount) + flt(self.total_additional_cost) + flt(self.tax_cost_total)
		self.total_landed_cost_import = (
			flt(self.total_base_amount_import) + flt(self.total_additional_cost_import) + flt(self.tax_cost_total_import)
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

		shipment = getattr(self, "_shipment_doc", None) or frappe.get_doc("Import Shipment", self.import_shipment)
		self._shipment_doc = shipment
		breakdown = getattr(self, "_component_breakdown", None) or self._allocate_cost_components(shipment)
		per_item_costs = breakdown["items"]

		self.set("allocations", [])

		for item in shipment.items:
			cost_detail = per_item_costs.get(item.name) or self._zero_breakdown_row()
			quantity = flt(item.quantity or 0)

			base_amount_import = flt(item.base_amount or 0)
			base_amount_local = flt(item.base_amount_local or 0) or self._convert_to_local(base_amount_import)

			foreign_local = flt(cost_detail["foreign_local"])
			local_local = flt(cost_detail["local_local"])
			tax_local = flt(cost_detail["tax_local"])
			foreign_import = flt(cost_detail["foreign_import"])
			local_import = flt(cost_detail["local_import"])
			tax_import = flt(cost_detail["tax_import"])

			additional_cost_local = foreign_local + local_local
			additional_cost_import = foreign_import + local_import
			allocation_ratio = (
				(additional_cost_local / flt(self.total_additional_cost))
				if flt(self.total_additional_cost)
				else 0
			)

			landed_cost_local = base_amount_local + additional_cost_local + tax_local
			landed_cost_import = base_amount_import + additional_cost_import + tax_import

			landed_rate_local = landed_cost_local / quantity if quantity else 0
			landed_rate_import = landed_cost_import / quantity if quantity else 0

			self.append(
				"allocations",
				{
					"shipment_item": item.name,
					"product": item.product,
					"import_currency": self.shipment_currency,
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

	def _build_product_summary(self):
		if not self.import_shipment:
			self.product_summaries = []
			self.estimated_total_net_profit = 0
			return

		shipment = getattr(self, "_shipment_doc", None) or frappe.get_doc("Import Shipment", self.import_shipment)
		self._shipment_doc = shipment
		existing_summary = {row.shipment_item: row for row in self.product_summaries}
		breakdown = getattr(self, "_component_breakdown", None) or self._allocate_cost_components(shipment)
		per_item_costs = breakdown["items"]

		self.set("product_summaries", [])

		total_net_profit = 0

		for item in shipment.items:
			quantity = flt(item.quantity or 0)
			base_amount_import = flt(item.base_amount or 0)
			base_amount_local = flt(item.base_amount_local or 0) or self._convert_to_local(base_amount_import)

			cost_detail = per_item_costs.get(item.name) or self._zero_breakdown_row()
			foreign_local = flt(cost_detail["foreign_local"])
			local_local = flt(cost_detail["local_local"])
			tax_local = flt(cost_detail["tax_local"])
			total_local_cost = base_amount_local + foreign_local + local_local + tax_local

			per_ton_foreign = (foreign_local / quantity) if quantity else 0
			per_ton_local = (local_local / quantity) if quantity else 0
			per_ton_tax = (tax_local / quantity) if quantity else 0
			per_ton_landed = (total_local_cost / quantity) if quantity else 0
			per_kg_landed = (per_ton_landed / 1000) if quantity else 0

			price_per_ton_import = (base_amount_import / quantity) if quantity else 0
			price_per_ton_local = (base_amount_local / quantity) if quantity else 0

			existing_row = existing_summary.get(item.name)
			selling_price = (
				flt(existing_row.selling_price_per_kg)
				if existing_row and existing_row.selling_price_per_kg is not None
				else flt(self.default_selling_price_per_kg or 0)
			)
			profit_tax_percent = (
				flt(existing_row.profit_tax_percent)
				if existing_row and existing_row.profit_tax_percent is not None
				else flt(self.profit_tax_percent or 0)
			)

			gross_profit_per_kg = selling_price - per_kg_landed
			net_profit_per_kg = gross_profit_per_kg * (1 - (profit_tax_percent / 100))
			total_net = net_profit_per_kg * quantity * 1000
			total_net_profit += total_net

			self.append(
				"product_summaries",
				{
					"shipment_item": item.name,
					"product": item.product,
					"import_currency": self.shipment_currency,
					"quantity_tons": quantity,
					"price_per_ton_import": price_per_ton_import,
					"price_per_ton_local": price_per_ton_local,
					"foreign_cost_per_ton": per_ton_foreign,
					"local_cost_per_ton": per_ton_local,
					"tax_cost_per_ton": per_ton_tax,
					"landing_cost_per_ton": per_ton_landed,
					"landing_cost_per_kg": per_kg_landed,
					"selling_price_per_kg": selling_price,
					"gross_profit_per_kg": gross_profit_per_kg,
					"profit_tax_percent": profit_tax_percent,
					"net_profit_per_kg": net_profit_per_kg,
					"total_net_profit": total_net,
				},
			)

		self.estimated_total_net_profit = total_net_profit

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

	def _sync_shipment_allocations(self, lock: bool = False):
		if not self.import_shipment:
			return None

		shipment = frappe.get_doc("Import Shipment", self.import_shipment)
		# Allow system-driven updates on submitted shipments
		shipment.flags.ignore_validate_update_after_submit = True
		item_map = {row.shipment_item: row for row in self.allocations}

		for item in shipment.items:
			allocation = item_map.get(item.name)
			if not allocation:
				continue
			item.flags.ignore_validate_update_after_submit = True

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

		if lock:
			shipment.landing_cost_status = "Locked"
			shipment.landing_cost_note = f"Landed cost locked via {self.name}"
		elif shipment.landing_cost_status != "Locked":
			status_note = f"Landed cost in review via {self.name}"
			shipment.landing_cost_status = "In Review"
			shipment.landing_cost_note = status_note

		shipment.save(ignore_permissions=True)
		return shipment

	def _lock_shipment_costs(self):
		if not self.import_shipment:
			return

		shipment = self._sync_shipment_allocations(lock=True)
		if not shipment:
			return

		self._update_purchase_order_receipts(shipment)

		# Update downstream stock entry items
		for item in shipment.items:
			item.flags.ignore_validate_update_after_submit = True
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
			batch_doc.flags.ignore_validate_update_after_submit = True
			stock_ledger.update_stock_entry_balances(batch_doc)

		self.locked_on = now_datetime()
		self.lock_note = f"Locked via worksheet {self.name}"

	def _revert_shipment_lock(self):
		if not self.import_shipment:
			return
		shipment = frappe.get_doc("Import Shipment", self.import_shipment)
		if shipment.landing_cost_status != "Locked":
			return

		shipment.flags.ignore_validate_update_after_submit = True

		for item in shipment.items:
			item.flags.ignore_validate_update_after_submit = True
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
			batch_doc.flags.ignore_validate_update_after_submit = True
			for row in batch_doc.items:
				row.flags.ignore_validate_update_after_submit = True
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

	# -------------------------------------------------------------------------
	# Cost breakdown helpers

	def _allocate_cost_components(self, shipment):
		item_quantities = {item.name: flt(item.quantity or 0) for item in shipment.items}
		item_base_import = {item.name: flt(item.base_amount or 0) for item in shipment.items}
		item_base_local = {}
		for item in shipment.items:
			local_val = flt(item.base_amount_local or 0)
			if not local_val:
				local_val = self._convert_to_local(flt(item.base_amount or 0))
			item_base_local[item.name] = local_val

		breakdown = {
			"items": {item.name: self._zero_breakdown_row() for item in shipment.items},
			"totals": {
				"local": defaultdict(float),
				"import": defaultdict(float),
			},
		}

		component_groups = defaultdict(list)
		tax_rows = []
		for row in self.cost_components:
			bucket = self._normalise_cost_bucket(row.cost_bucket)
			if bucket == "tax":
				tax_rows.append(row)
			else:
				component_groups[bucket].append(row)

		# Explicit tax table entries
		for row in getattr(self, "taxes", []):
			tax_rows.append(row)

		subtotal_local = {name: item_base_local.get(name, 0) for name in item_base_local}

		for bucket in ("foreign", "local"):
			for row in component_groups.get(bucket, []):
				self._normalise_component_row(row)
				allocations = self._distribute_component_amount(
					row, shipment, item_quantities, item_base_import, item_base_local, subtotal_local
				)
				for item_name, amounts in allocations.items():
					entry = breakdown["items"].setdefault(item_name, self._zero_breakdown_row())
					entry[f"{bucket}_local"] += amounts["local"]
					entry[f"{bucket}_import"] += amounts["import"]
					entry["total_local"] += amounts["local"]
					entry["total_import"] += amounts["import"]
					breakdown["totals"]["local"][bucket] += amounts["local"]
					breakdown["totals"]["import"][bucket] += amounts["import"]
					subtotal_local[item_name] = subtotal_local.get(item_name, 0) + amounts["local"]

		for row in tax_rows:
			self._normalise_component_row(row)
			allocations = self._distribute_component_amount(
				row, shipment, item_quantities, item_base_import, item_base_local, subtotal_local
			)
			for item_name, amounts in allocations.items():
				entry = breakdown["items"].setdefault(item_name, self._zero_breakdown_row())
				entry["tax_local"] += amounts["local"]
				entry["tax_import"] += amounts["import"]
				entry["total_local"] += amounts["local"]
				entry["total_import"] += amounts["import"]
				breakdown["totals"]["local"]["tax"] += amounts["local"]
				breakdown["totals"]["import"]["tax"] += amounts["import"]

		return breakdown

	def _distribute_component_amount(
		self, row, shipment, item_quantities, item_base_import, item_base_local, subtotal_local
	):
		is_tax = getattr(row, "doctype", "") == "Landing Cost Tax"

		if row.apply_to_item:
			if row.apply_to_item not in item_quantities:
				frappe.throw(_("Cost component {0} references an unknown shipment item.").format(row.cost_type))
			target_items = [row.apply_to_item]
		else:
			target_items = list(item_quantities.keys())
		if not target_items:
			return {}

		scope = (row.cost_scope or "Total Amount").strip() or "Total Amount"
		result = {}

		if scope == "Total Amount":
			if is_tax:
				frappe.throw(_("Taxes must be a percentage-based scope."))
			total_amount = flt(row.amount or 0)
			if total_amount <= 0:
				row.converted_amount = 0
				return {}
			basis = self._get_allocation_basis_for_targets(shipment, target_items)
			total_basis = sum(basis.values())
			if not total_basis:
				frappe.throw(_("Cannot distribute component {0} because allocation basis is zero.").format(row.cost_type))
			for item_name in target_items:
				share = basis[item_name] / total_basis
				amount_currency = total_amount * share
				result[item_name] = self._convert_component_amount(row, amount_currency)

		elif scope == "Per Ton":
			if is_tax:
				frappe.throw(_("Taxes must be a percentage-based scope."))
			rate = flt(row.amount or 0)
			if rate == 0:
				row.converted_amount = 0
				return {}
			for item_name in target_items:
				qty = item_quantities.get(item_name) or 0
				if not qty:
					continue
				amount_currency = rate * qty
				result[item_name] = self._convert_component_amount(row, amount_currency)

		elif scope == "Per Kg":
			if is_tax:
				frappe.throw(_("Taxes must be a percentage-based scope."))
			rate = flt(row.amount or 0)
			if rate == 0:
				row.converted_amount = 0
				return {}
			for item_name in target_items:
				qty = (item_quantities.get(item_name) or 0) * 1000
				if not qty:
					continue
				amount_currency = rate * qty
				result[item_name] = self._convert_component_amount(row, amount_currency)

		elif scope == "Percent of CIF":
			percent = self._get_component_percent(row, is_tax)
			if percent == 0:
				frappe.throw(_("Set a percent for component {0}.").format(row.cost_type))
			for item_name in target_items:
				base_value = self._get_base_value_for_percent(row, item_base_import[item_name], item_base_local[item_name])
				amount_currency = base_value * percent / 100
				result[item_name] = self._convert_component_amount(row, amount_currency)

		elif scope == "Percent of Landed Cost":
			percent = self._get_component_percent(row, is_tax)
			if percent == 0:
				frappe.throw(_("Set a percent for component {0}.").format(row.cost_type))
			for item_name in target_items:
				base_value_local = subtotal_local.get(item_name, 0)
				base_in_component_currency = self._convert_local_to_component_currency(row, base_value_local)
				amount_currency = base_in_component_currency * percent / 100
				result[item_name] = self._convert_component_amount(row, amount_currency)
		else:
			frappe.throw(_("Unknown cost scope '{0}' for component {1}.").format(scope, row.cost_type))

		row.converted_amount = sum(entry["local"] for entry in result.values())
		return result

	def _get_component_percent(self, row, is_tax: bool) -> float:
		if is_tax:
			# Prefer explicit override via amount when used as a percent, else default table percentages
			if hasattr(row, "percentage") and (row.percentage is not None):
				return flt(row.percentage)
			key = (row.cost_type or "").strip().lower()
			return TAX_PERCENT_BY_TYPE.get(key, 0.0)

		return flt(getattr(row, "percentage_rate", 0) or 0)

	def _normalise_cost_bucket(self, bucket_value):
		value = (bucket_value or "Foreign Cost").lower()
		if "local" in value:
			return "local"
		if "tax" in value:
			return "tax"
		return "foreign"

	def _normalise_component_row(self, row):
		bucket = self._normalise_cost_bucket(getattr(row, "cost_bucket", None))
		if not row.currency:
			if bucket == "foreign":
				row.currency = "USD"
			elif bucket == "local":
				row.currency = "ETB"

		row.currency = row.currency or self.currency or self.shipment_currency
		if row.currency == self.currency:
			row.exchange_rate = 1
		elif row.currency == self.shipment_currency:
			row.exchange_rate = row.exchange_rate or self.shipment_exchange_rate or 0
		else:
			row.exchange_rate = row.exchange_rate or 0

	def _component_exchange_rate(self, row):
		if row.currency == self.currency:
			return 1.0
		if row.currency == self.shipment_currency:
			rate = flt(row.exchange_rate or 0) or flt(self.shipment_exchange_rate or 0)
			if rate <= 0:
				frappe.throw(_("Set Exchange Rate (Shipment → Worksheet) to convert shipment currency components."))
			return rate
		rate = flt(row.exchange_rate or 0)
		if rate <= 0:
			frappe.throw(_("Please set an exchange rate for component {0}.").format(row.cost_type))
		return rate

	def _convert_component_amount(self, row, amount_currency):
		rate = self._component_exchange_rate(row)
		local_amount = flt(amount_currency or 0) * rate

		if row.currency == self.shipment_currency:
			import_amount = flt(amount_currency or 0)
		elif self.shipment_currency == self.currency:
			import_amount = flt(local_amount)
		else:
			ship_rate = flt(self.shipment_exchange_rate or 0)
			import_amount = (local_amount / ship_rate) if ship_rate > 0 else 0

		return {"local": local_amount, "import": import_amount}

	def _convert_local_to_component_currency(self, row, local_amount):
		if row.currency == self.currency:
			return flt(local_amount)
		rate = self._component_exchange_rate(row)
		return flt(local_amount) / rate if rate else 0

	def _get_base_value_for_percent(self, row, base_import, base_local):
		if row.currency == self.shipment_currency:
			return flt(base_import)
		if row.currency == self.currency:
			return flt(base_local)
		rate = self._component_exchange_rate(row)
		return flt(base_local) / rate if rate else 0

	def _get_allocation_basis_for_targets(self, shipment, target_items):
		full_basis = self._get_allocation_basis(shipment)
		return {name: full_basis.get(name, 0) for name in target_items}

	def _zero_breakdown_row(self):
		return {
			"foreign_local": 0.0,
			"foreign_import": 0.0,
			"local_local": 0.0,
			"local_import": 0.0,
			"tax_local": 0.0,
			"tax_import": 0.0,
			"total_local": 0.0,
			"total_import": 0.0,
		}


def get_dashboard_data():
	return {
		"fieldname": "import_shipment",
		"transactions": [],
		"internal_links": {
			"Import Shipment": ["import_shipment"],
			"Purchase Order": ["purchase_order"],
		},
	}


@frappe.whitelist()
def preview_totals(doc):
	"""Return recalculated totals (including taxes) for an unsaved worksheet client preview."""
	if isinstance(doc, str):
		doc = json.loads(doc)

	worksheet = frappe.get_doc(doc)
	worksheet._ensure_shipment_context()
	worksheet._calculate_totals()
	worksheet._build_allocations()

	return {
		"total_additional_cost": worksheet.total_additional_cost,
		"total_additional_cost_import": worksheet.total_additional_cost_import,
		"tax_cost_total": worksheet.tax_cost_total,
		"tax_cost_total_import": worksheet.tax_cost_total_import,
		"total_landed_cost": worksheet.total_landed_cost,
		"total_landed_cost_import": worksheet.total_landed_cost_import,
		"avg_landed_cost": worksheet.avg_landed_cost,
		"avg_landed_cost_import": worksheet.avg_landed_cost_import,
		"foreign_cost_total": worksheet.foreign_cost_total,
		"local_cost_total": worksheet.local_cost_total,
		"total_quantity": worksheet.total_quantity,
	}
