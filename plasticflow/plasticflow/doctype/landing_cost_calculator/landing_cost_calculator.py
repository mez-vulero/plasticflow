import json
from collections import defaultdict

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


TAX_PERCENT_BY_TYPE = {
	"import duty tax 5%": 5.0,
	"excise tax 3%": 3.0,
	"sur tax 10%": 10.0,
	"social welfare tax 3%": 3.0,
	"withholding tax 3%": 3.0,
	"vat 15%": 15.0,
}


class LandingCostCalculator(Document):
	"""Standalone landing-cost calculator for profitability forecasting.

	Unlike Landing Cost Worksheet this document has no link to Import Shipment,
	no status workflow, and no side effects on other documents.
	"""

	def validate(self):
		self._ensure_defaults()
		self._normalise_items()
		self._calculate()

	# -------------------------------------------------------------------------
	# Setup helpers

	def _ensure_defaults(self):
		if not self.currency:
			self.currency = frappe.db.get_default("currency") or "ETB"
		if not self.import_currency:
			self.import_currency = "USD"
		if not self.exchange_rate or flt(self.exchange_rate) <= 0:
			if self.currency == self.import_currency:
				self.exchange_rate = 1
			else:
				self.exchange_rate = 1

	def _normalise_items(self):
		for item in self.items:
			quantity = flt(item.quantity_tons or 0)
			price_per_ton = flt(item.price_per_ton_import or 0)
			base_amount = flt(item.base_amount_import or 0)

			if not base_amount and price_per_ton and quantity:
				base_amount = price_per_ton * quantity
				item.base_amount_import = base_amount
			elif base_amount and not price_per_ton and quantity:
				item.price_per_ton_import = base_amount / quantity

			item.base_amount_import_calc = flt(item.base_amount_import or 0)
			item.base_amount_local = flt(item.base_amount_import or 0) * flt(self.exchange_rate or 0)

			if item.selling_price_per_kg in (None, 0, 0.0) and self.default_selling_price_per_kg:
				item.selling_price_per_kg = self.default_selling_price_per_kg
			if item.profit_tax_percent in (None, 0, 0.0) and self.default_profit_tax_percent:
				item.profit_tax_percent = self.default_profit_tax_percent

	# -------------------------------------------------------------------------
	# Core calculation

	def _calculate(self):
		item_names = [item.name for item in self.items]
		item_quantities = {item.name: flt(item.quantity_tons or 0) for item in self.items}
		item_base_import = {item.name: flt(item.base_amount_import or 0) for item in self.items}
		item_base_local = {
			item.name: flt(item.base_amount_import or 0) * flt(self.exchange_rate or 0)
			for item in self.items
		}

		breakdown = {
			name: {
				"foreign_local": 0.0,
				"foreign_import": 0.0,
				"local_local": 0.0,
				"local_import": 0.0,
				"tax_local": 0.0,
				"tax_import": 0.0,
			}
			for name in item_names
		}

		taxable_base_local = dict(item_base_local)
		taxable_base_import = dict(item_base_import)
		running_subtotal_local = dict(item_base_local)

		totals_local = defaultdict(float)
		totals_import = defaultdict(float)

		foreign_rows, local_rows, tax_rows = self._partition_cost_rows()

		for bucket, rows in (("foreign", foreign_rows), ("local", local_rows)):
			for row in rows:
				self._normalise_component_row(row)
				allocations = self._distribute_component(
					row,
					item_quantities,
					item_base_import,
					item_base_local,
					running_subtotal_local,
					is_tax=False,
				)
				for item_name, amounts in allocations.items():
					entry = breakdown.setdefault(item_name, self._zero_entry())
					entry[f"{bucket}_local"] += amounts["local"]
					entry[f"{bucket}_import"] += amounts["import"]
					totals_local[bucket] += amounts["local"]
					totals_import[bucket] += amounts["import"]
					running_subtotal_local[item_name] = (
						running_subtotal_local.get(item_name, 0) + amounts["local"]
					)
					if self._is_taxable_component(row):
						taxable_base_local[item_name] = (
							taxable_base_local.get(item_name, 0) + amounts["local"]
						)
						taxable_base_import[item_name] = (
							taxable_base_import.get(item_name, 0) + amounts["import"]
						)

		for row in tax_rows:
			self._normalise_component_row(row)
			allocations = self._distribute_component(
				row,
				item_quantities,
				taxable_base_import,
				taxable_base_local,
				taxable_base_local,
				is_tax=True,
			)
			for item_name, amounts in allocations.items():
				entry = breakdown.setdefault(item_name, self._zero_entry())
				entry["tax_local"] += amounts["local"]
				entry["tax_import"] += amounts["import"]
				totals_local["tax"] += amounts["local"]
				totals_import["tax"] += amounts["import"]

		# Write back to item rows
		total_quantity = 0.0
		total_base_local = 0.0
		total_base_import = 0.0
		total_landed_local = 0.0
		total_landed_import = 0.0
		total_net_profit = 0.0

		for item in self.items:
			entry = breakdown.get(item.name, self._zero_entry())
			quantity = flt(item.quantity_tons or 0)
			base_local = item_base_local.get(item.name, 0)
			base_import = item_base_import.get(item.name, 0)

			foreign_local = flt(entry["foreign_local"])
			local_local = flt(entry["local_local"])
			tax_local = flt(entry["tax_local"])
			foreign_import = flt(entry["foreign_import"])
			local_import = flt(entry["local_import"])
			tax_import = flt(entry["tax_import"])

			landed_local = base_local + foreign_local + local_local + tax_local
			landed_import = base_import + foreign_import + local_import + tax_import

			item.foreign_cost_total = foreign_local
			item.local_cost_total = local_local
			item.tax_cost_total = tax_local
			item.landed_cost_total = landed_local
			item.landed_cost_per_ton = (landed_local / quantity) if quantity else 0
			item.landed_cost_per_kg = item.landed_cost_per_ton / 1000 if quantity else 0
			item.landed_cost_total_import = landed_import
			item.landed_cost_per_ton_import = (landed_import / quantity) if quantity else 0
			item.landed_cost_per_kg_import = item.landed_cost_per_ton_import / 1000 if quantity else 0

			selling_price = flt(item.selling_price_per_kg or 0)
			profit_tax_percent = flt(item.profit_tax_percent or 0)
			gross_profit_per_kg = selling_price - flt(item.landed_cost_per_kg)
			net_profit_per_kg = gross_profit_per_kg * (1 - profit_tax_percent / 100)
			net_total = net_profit_per_kg * quantity * 1000

			item.gross_profit_per_kg = gross_profit_per_kg
			item.net_profit_per_kg = net_profit_per_kg
			item.total_net_profit = net_total

			total_quantity += quantity
			total_base_local += base_local
			total_base_import += base_import
			total_landed_local += landed_local
			total_landed_import += landed_import
			total_net_profit += net_total

		self.total_quantity = total_quantity
		self.total_base_amount_local = total_base_local
		self.total_base_amount_import = total_base_import
		self.total_foreign_cost = flt(totals_local.get("foreign", 0))
		self.total_local_cost = flt(totals_local.get("local", 0))
		self.total_tax_cost = flt(totals_local.get("tax", 0))
		self.total_landed_cost = total_landed_local
		self.total_landed_cost_import = total_landed_import
		self.avg_landed_cost_per_ton = (
			(total_landed_local / total_quantity) if total_quantity else 0
		)
		self.avg_landed_cost_per_kg = (
			self.avg_landed_cost_per_ton / 1000 if total_quantity else 0
		)
		self.avg_landed_cost_per_ton_import = (
			(total_landed_import / total_quantity) if total_quantity else 0
		)
		self.estimated_total_net_profit = total_net_profit

	# -------------------------------------------------------------------------
	# Component distribution (mirrors Landing Cost Worksheet logic)

	def _partition_cost_rows(self):
		foreign_rows, local_rows, tax_rows = [], [], []
		for row in self.costs or []:
			bucket = (row.cost_bucket or "Foreign Cost").lower()
			if "local" in bucket:
				local_rows.append(row)
			else:
				foreign_rows.append(row)
		for row in self.taxes or []:
			tax_rows.append(row)
		return foreign_rows, local_rows, tax_rows

	def _distribute_component(
		self,
		row,
		item_quantities,
		item_base_import,
		item_base_local,
		subtotal_local,
		is_tax,
	):
		if row.apply_to_item:
			if row.apply_to_item not in item_quantities:
				frappe.throw(
					_("Cost component {0} references an unknown item row.").format(row.cost_type)
				)
			target_items = [row.apply_to_item]
		else:
			target_items = list(item_quantities.keys())

		if not target_items:
			return {}

		scope = (row.cost_scope or ("Percent of CIF" if is_tax else "Total Amount")).strip()
		result = {}

		if scope == "Total Amount":
			if is_tax:
				frappe.throw(_("Taxes must be a percentage-based scope."))
			total_amount = flt(row.amount or 0)
			if total_amount <= 0:
				row.converted_amount = 0
				return {}
			basis = self._allocation_basis(target_items, item_quantities, item_base_import)
			total_basis = sum(basis.values())
			if not total_basis:
				frappe.throw(
					_("Cannot distribute component {0} — allocation basis is zero.").format(row.cost_type)
				)
			for item_name in target_items:
				share = basis[item_name] / total_basis
				result[item_name] = self._convert(row, total_amount * share)

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
				result[item_name] = self._convert(row, rate * qty)

		elif scope == "Per Kg":
			if is_tax:
				frappe.throw(_("Taxes must be a percentage-based scope."))
			rate = flt(row.amount or 0)
			if rate == 0:
				row.converted_amount = 0
				return {}
			for item_name in target_items:
				qty_kg = (item_quantities.get(item_name) or 0) * 1000
				if not qty_kg:
					continue
				result[item_name] = self._convert(row, rate * qty_kg)

		elif scope == "Percent of CIF":
			percent = self._component_percent(row, is_tax)
			if percent == 0:
				frappe.throw(_("Set a percent for component {0}.").format(row.cost_type))
			for item_name in target_items:
				base_in_component_ccy = self._base_for_percent(
					row, item_base_import[item_name], item_base_local[item_name]
				)
				result[item_name] = self._convert(row, base_in_component_ccy * percent / 100)

		elif scope == "Percent of Landed Cost":
			percent = self._component_percent(row, is_tax)
			if percent == 0:
				frappe.throw(_("Set a percent for component {0}.").format(row.cost_type))
			for item_name in target_items:
				base_local = subtotal_local.get(item_name, 0)
				base_in_component_ccy = self._local_to_component_ccy(row, base_local)
				result[item_name] = self._convert(row, base_in_component_ccy * percent / 100)

		else:
			frappe.throw(_("Unknown cost scope '{0}' for component {1}.").format(scope, row.cost_type))

		row.converted_amount = sum(entry["local"] for entry in result.values())
		return result

	def _allocation_basis(self, target_items, item_quantities, item_base_import):
		method = (self.allocation_method or "By Value").lower()
		basis = {}
		for name in target_items:
			if method == "by quantity":
				value = flt(item_quantities.get(name) or 0)
			else:
				value = flt(item_base_import.get(name) or 0)
			basis[name] = max(value, 0)
		return basis

	def _component_percent(self, row, is_tax):
		if is_tax:
			if getattr(row, "percentage", None) not in (None, 0, 0.0):
				return flt(row.percentage)
			key = (row.cost_type or "").strip().lower()
			return TAX_PERCENT_BY_TYPE.get(key, 0.0)
		return flt(getattr(row, "percentage_rate", 0) or 0)

	def _normalise_component_row(self, row):
		if not row.currency:
			bucket = (getattr(row, "cost_bucket", "") or "").lower()
			if "local" in bucket:
				row.currency = self.currency
			else:
				row.currency = self.import_currency
		if not row.exchange_rate or flt(row.exchange_rate) <= 0:
			if row.currency == self.currency:
				row.exchange_rate = 1
			elif row.currency == self.import_currency:
				row.exchange_rate = flt(self.exchange_rate or 0) or 1
			else:
				row.exchange_rate = 1

	def _component_exchange_rate(self, row):
		if row.currency == self.currency:
			return 1.0
		if row.currency == self.import_currency:
			rate = flt(row.exchange_rate or 0) or flt(self.exchange_rate or 0)
			if rate <= 0:
				frappe.throw(_("Set Exchange Rate (Import → Local) first."))
			return rate
		rate = flt(row.exchange_rate or 0)
		if rate <= 0:
			frappe.throw(_("Set an exchange rate for component {0}.").format(row.cost_type))
		return rate

	def _convert(self, row, amount_in_component_ccy):
		rate_to_local = self._component_exchange_rate(row)
		local_amount = flt(amount_in_component_ccy or 0) * rate_to_local

		if row.currency == self.import_currency:
			import_amount = flt(amount_in_component_ccy or 0)
		elif self.import_currency == self.currency:
			import_amount = flt(local_amount)
		else:
			ship_rate = flt(self.exchange_rate or 0)
			import_amount = (local_amount / ship_rate) if ship_rate > 0 else 0

		return {"local": local_amount, "import": import_amount}

	def _local_to_component_ccy(self, row, local_amount):
		if row.currency == self.currency:
			return flt(local_amount)
		rate = self._component_exchange_rate(row)
		return flt(local_amount) / rate if rate else 0

	def _base_for_percent(self, row, base_import, base_local):
		if row.currency == self.import_currency:
			return flt(base_import)
		if row.currency == self.currency:
			return flt(base_local)
		rate = self._component_exchange_rate(row)
		return flt(base_local) / rate if rate else 0

	def _is_taxable_component(self, row):
		value = getattr(row, "is_taxable", None)
		if value in (None, ""):
			return True
		return bool(int(value))

	def _zero_entry(self):
		return {
			"foreign_local": 0.0,
			"foreign_import": 0.0,
			"local_local": 0.0,
			"local_import": 0.0,
			"tax_local": 0.0,
			"tax_import": 0.0,
		}


@frappe.whitelist()
def preview_totals(doc):
	"""Recalculate totals for an unsaved calculator — client-side live preview."""
	if isinstance(doc, str):
		doc = json.loads(doc)

	calc = frappe.get_doc(doc)
	calc._ensure_defaults()
	calc._normalise_items()
	calc._calculate()

	return {
		"total_quantity": calc.total_quantity,
		"total_base_amount_local": calc.total_base_amount_local,
		"total_base_amount_import": calc.total_base_amount_import,
		"total_foreign_cost": calc.total_foreign_cost,
		"total_local_cost": calc.total_local_cost,
		"total_tax_cost": calc.total_tax_cost,
		"total_landed_cost": calc.total_landed_cost,
		"total_landed_cost_import": calc.total_landed_cost_import,
		"avg_landed_cost_per_ton": calc.avg_landed_cost_per_ton,
		"avg_landed_cost_per_kg": calc.avg_landed_cost_per_kg,
		"avg_landed_cost_per_ton_import": calc.avg_landed_cost_per_ton_import,
		"estimated_total_net_profit": calc.estimated_total_net_profit,
		"items": [
			{
				"name": item.name,
				"base_amount_import": item.base_amount_import,
				"base_amount_local": item.base_amount_local,
				"price_per_ton_import": item.price_per_ton_import,
				"foreign_cost_total": item.foreign_cost_total,
				"local_cost_total": item.local_cost_total,
				"tax_cost_total": item.tax_cost_total,
				"landed_cost_total": item.landed_cost_total,
				"landed_cost_per_ton": item.landed_cost_per_ton,
				"landed_cost_per_kg": item.landed_cost_per_kg,
				"landed_cost_total_import": item.landed_cost_total_import,
				"landed_cost_per_ton_import": item.landed_cost_per_ton_import,
				"landed_cost_per_kg_import": item.landed_cost_per_kg_import,
				"gross_profit_per_kg": item.gross_profit_per_kg,
				"net_profit_per_kg": item.net_profit_per_kg,
				"total_net_profit": item.total_net_profit,
			}
			for item in calc.items
		],
	}
