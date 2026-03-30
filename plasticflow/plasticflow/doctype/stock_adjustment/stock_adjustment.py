import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

from plasticflow.stock import uom as stock_uom
from plasticflow.stock.adjustment import QTY_TOLERANCE, StockAdjustmentMixin


class StockAdjustment(StockAdjustmentMixin, Document):
	"""Manual stock adjustments allocated across shipments for a product."""

	def validate(self):
		if not self.posting_date:
			self.posting_date = nowdate()
		self._set_item_defaults()

	def before_submit(self):
		self._apply_adjustments()

	def on_cancel(self):
		self._apply_adjustments(reverse=True)

	def _set_item_defaults(self):
		for item in self.items:
			if item.product and not item.product_name:
				item.product_name = frappe.db.get_value("Product", item.product, "product_name")
			if item.product and not item.uom:
				item.uom = frappe.db.get_value("Product", item.product, "uom")

	def _apply_adjustments(self, reverse: bool = False):
		location_type = self.location_type or "Warehouse"
		warehouse = self.warehouse if location_type == "Warehouse" else None
		sign = -1 if reverse else 1

		touched: dict[str, object] = {}

		for item in self.items:
			qty = flt(item.quantity or 0)
			if qty == 0 or not item.product:
				continue
			stock_uom_name = frappe.db.get_value("Product", item.product, "uom") or item.uom
			qty_stock = stock_uom.convert_quantity(qty, item.uom, stock_uom_name) * sign
			self._apply_adjustment_line(
				item.product,
				qty_stock,
				stock_uom_name=stock_uom_name,
				location_type=location_type,
				warehouse=warehouse,
				reverse=reverse,
				touched=touched,
			)

		self._save_touched_batches(touched)
