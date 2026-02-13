import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

from plasticflow.stock import ledger as stock_ledger
from plasticflow.stock import uom as stock_uom

QTY_TOLERANCE = 0.0001


class StockAdjustment(Document):
	"""Manual stock adjustments scoped to an import shipment."""

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
		if not self.import_shipment:
			frappe.throw(_("Import Shipment is required."))
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
				location_type=location_type,
				warehouse=warehouse,
				touched=touched,
			)

		for batch_doc in touched.values():
			batch_doc.flags.ignore_validate_update_after_submit = True
			for row in batch_doc.items:
				row.flags.ignore_validate_update_after_submit = True
			batch_doc._update_item_balances()
			batch_doc._update_totals()
			batch_doc._set_status()
			batch_doc.save(ignore_permissions=True)
			stock_ledger.update_stock_entry_balances(batch_doc)

	def _apply_adjustment_line(self, product, qty_stock, *, location_type, warehouse, touched):
		batches = self._get_adjustment_batches(product, location_type, warehouse)
		if not batches:
			frappe.throw(
				_("No stock entry items found for {0} in shipment {1}.").format(
					product, self.import_shipment
				)
			)

		if qty_stock > 0:
			target = batches[-1]
			self._update_batch_item(target, qty_stock, touched)
			return

		remaining = abs(qty_stock)
		for batch in batches:
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
		child_table = "`tabStock Entry Items`"
		parent_table = "`tabStock Entries`"

		conditions = ["se.docstatus = 1", "sei.product = %s", "se.import_shipment = %s"]
		values: list = [product, self.import_shipment]

		if location_type == "Customs":
			conditions.append("se.status = 'At Customs'")
		else:
			conditions.append("se.status in ('Available', 'Reserved', 'Partially Issued', 'Depleted')")
			if warehouse:
				conditions.append("se.warehouse = %s")
				values.append(warehouse)

		query = f"""
			select
				sei.name as child_name,
				se.name as batch_name,
				se.status as status,
				se.warehouse as warehouse,
				coalesce(se.arrival_date, se.creation) as arrival_marker,
				se.creation as creation,
				coalesce(sei.reserved_qty,0) as reserved_qty,
				(coalesce(sei.received_qty,0) - coalesce(sei.reserved_qty,0) - coalesce(sei.issued_qty,0)) as available_qty
			from {child_table} sei
			inner join {parent_table} se on se.name = sei.parent
			where {" and ".join(conditions)}
			order by arrival_marker, se.creation
		"""
		return frappe.db.sql(query, tuple(values), as_dict=True)
