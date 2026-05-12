import frappe
from frappe import _
from frappe.utils import flt

from plasticflow.stock import availability as stock_availability
from plasticflow.stock import ledger as stock_ledger
from plasticflow.stock import uom as stock_uom

QTY_TOLERANCE = 0.0001


class StockAdjustmentMixin:
	"""Shared batch-adjustment logic for Stock Adjustment and Stock Reconciliation."""

	def _apply_adjustment_line(
		self,
		product,
		qty_stock,
		*,
		stock_uom_name,
		location_type,
		warehouse,
		reverse,
		touched,
	):
		batches = self._get_adjustment_batches(product, location_type, warehouse)
		if not batches:
			frappe.throw(
				_("No stock entry items found for {0}.").format(product)
			)

		if qty_stock > 0:
			remaining = qty_stock
			batch_iter = batches if reverse else reversed(batches)
			for batch in batch_iter:
				capacity = self._remaining_capacity(batch, stock_uom_name)
				if capacity is not None and capacity <= 0:
					continue
				apply_qty = remaining if capacity is None else min(capacity, remaining)
				if apply_qty <= 0:
					continue
				self._update_batch_item(batch, apply_qty, touched)
				remaining -= apply_qty
				if remaining <= QTY_TOLERANCE:
					return

			frappe.throw(
				_("Insufficient shipment capacity to add {0}. Short by {1} units.").format(
					product, f"{remaining:.3f}"
				)
			)

		remaining = abs(qty_stock)
		batch_iter = reversed(batches) if reverse else batches
		for batch in batch_iter:
			available = flt(batch.available_qty or 0)
			if available <= 0:
				continue
			reduce = min(available, remaining)
			self._update_batch_item(batch, -reduce, touched)
			remaining -= reduce
			if remaining <= QTY_TOLERANCE:
				return

		frappe.throw(
			_("Insufficient available stock to reduce {0}. Short by {1} units.").format(
				product, f"{remaining:.3f}"
			)
		)

	def _remaining_capacity(self, batch, stock_uom_name):
		if self.allow_over_capacity:
			return None
		original_qty = batch.get("original_qty")
		if original_qty is None:
			return None
		original_uom = batch.get("original_uom") or batch.get("uom") or stock_uom_name
		item_uom = batch.get("uom") or stock_uom_name
		original_stock = stock_uom.convert_quantity(original_qty, original_uom, stock_uom_name)
		received_stock = stock_uom.convert_quantity(batch.get("received_qty") or 0, item_uom, stock_uom_name)
		return max(flt(original_stock) - flt(received_stock), 0)

	def _update_batch_item(self, batch, delta_qty, touched):
		batch_doc = touched.get(batch.batch_name)
		if not batch_doc:
			batch_doc = frappe.get_doc("Stock Entries", batch.batch_name)
			touched[batch.batch_name] = batch_doc
		child = next((row for row in batch_doc.items if row.name == batch.child_name), None)
		if not child:
			frappe.throw(_("Stock Entry Item {0} not found in {1}.").format(batch.child_name, batch.batch_name))
		child.received_qty = max(flt(child.received_qty or 0) + flt(delta_qty or 0), 0)

	def _get_adjustment_batches(self, product, location_type, warehouse):
		# Adjustment tools need every in-status batch, including ones with
		# zero available stock — they may still have headroom against the
		# Import Shipment master quantity that we can top up into.
		return stock_availability.get_available_batches(
			product,
			location_type=location_type,
			warehouse=warehouse,
			fifo=True,
			include_zero=True,
		)

	def _save_touched_batches(self, touched):
		for batch_doc in touched.values():
			batch_doc.flags.ignore_validate_update_after_submit = True
			for row in batch_doc.items:
				row.flags.ignore_validate_update_after_submit = True
			batch_doc._update_item_balances()
			batch_doc._update_totals()
			batch_doc._set_status()
			batch_doc.save(ignore_permissions=True)
			stock_ledger.update_stock_entry_balances(batch_doc)
