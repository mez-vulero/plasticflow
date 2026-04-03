import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

from plasticflow.stock import uom as stock_uom
from plasticflow.stock.adjustment import QTY_TOLERANCE, StockAdjustmentMixin


class StockReconciliation(StockAdjustmentMixin, Document):
	"""Set target stock levels and let the system calculate and apply the difference."""

	def validate(self):
		if not self.posting_date:
			self.posting_date = nowdate()
		self._set_item_defaults()
		self._check_duplicates()
		self._compute_differences()

	def before_submit(self):
		self._compute_differences()

	def on_submit(self):
		has_changes = any(
			abs(flt(item.difference)) >= QTY_TOLERANCE
			for item in self.items
			if item.product
		)
		if not has_changes:
			frappe.msgprint(
				_("No differences found. Current stock already matches target quantities."),
				indicator="orange",
				alert=True,
			)
			return
		self._apply_reconciliation()

	def on_cancel(self):
		self._apply_reconciliation(reverse=True)

	def _set_item_defaults(self):
		for item in self.items:
			if item.product and not item.product_name:
				item.product_name = frappe.db.get_value("Product", item.product, "product_name")
			if item.product and not item.uom:
				item.uom = frappe.db.get_value("Product", item.product, "uom")

	def _check_duplicates(self):
		seen = set()
		for item in self.items:
			if not item.product:
				continue
			if item.product in seen:
				frappe.throw(_("Product {0} appears more than once.").format(item.product))
			seen.add(item.product)

	def _compute_differences(self):
		location_type = self.location_type or "Warehouse"
		warehouse = self.warehouse if location_type == "Warehouse" else None

		for item in self.items:
			if not item.product:
				continue
			batches = self._get_adjustment_batches(item.product, location_type, warehouse)
			item.current_qty = sum(flt(b.available_qty) for b in batches)
			item.difference = flt(item.target_qty) - flt(item.current_qty)

	def _apply_reconciliation(self, reverse=False):
		location_type = self.location_type or "Warehouse"
		warehouse = self.warehouse if location_type == "Warehouse" else None
		sign = -1 if reverse else 1
		touched: dict[str, object] = {}

		for item in self.items:
			diff = flt(item.difference)
			if abs(diff) < QTY_TOLERANCE or not item.product:
				continue
			stock_uom_name = frappe.db.get_value("Product", item.product, "uom") or item.uom
			qty_stock = stock_uom.convert_quantity(diff, item.uom, stock_uom_name) * sign
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


@frappe.whitelist()
def get_current_stock(product, location_type="Warehouse", warehouse=None):
	"""Return total available_qty for a product at the given location."""
	conditions = ["se.docstatus = 1", "sei.product = %s"]
	values = [product]

	if location_type == "Customs":
		conditions.append("se.status = 'At Customs'")
	else:
		conditions.append("se.status in ('Available', 'Reserved', 'Partially Issued', 'Depleted')")
		if warehouse:
			conditions.append("se.warehouse = %s")
			values.append(warehouse)

	result = frappe.db.sql(
		f"""
		select coalesce(sum(
			coalesce(sei.received_qty, 0) - coalesce(sei.reserved_qty, 0) - coalesce(sei.issued_qty, 0)
		), 0) as total_available
		from `tabStock Entry Items` sei
		inner join `tabStock Entries` se on se.name = sei.parent
		where {" and ".join(conditions)}
		""",
		tuple(values),
		as_dict=True,
	)

	return flt(result[0].total_available) if result else 0.0
