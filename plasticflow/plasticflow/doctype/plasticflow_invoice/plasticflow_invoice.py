import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

PAYMENT_TOLERANCE = 0.01


class PlasticflowInvoice(Document):
	"""Finance invoice generated after payment verification."""

	def validate(self):
		self._set_item_defaults()
		self._calculate_totals()
		if not self.status:
			self.status = "Pending"
		if not self.due_date:
			self.due_date = self.invoice_date or nowdate()
		self._ensure_alignment_with_sales_order()

	def on_submit(self):
		self._sync_sales_order_progress()
		self._maybe_create_gate_pass()

	def on_cancel(self):
		self._sync_sales_order_progress()
		if self.gate_pass:
			frappe.db.set_value("Gate Pass", self.gate_pass, "status", "Cancelled")
			frappe.db.set_value("Plasticflow Invoice", self.name, "gate_pass", None, update_modified=False)
			self.gate_pass = None
		frappe.db.set_value("Plasticflow Invoice", self.name, "sales_order", None, update_modified=False)
		self.sales_order = None

	def _set_item_defaults(self):
		for item in self.items:
			if item.product and not item.product_name:
				item.product_name = frappe.db.get_value("Product", item.product, "product_name")
			if item.quantity and item.rate:
				item.amount = (item.quantity or 0) * (item.rate or 0)

	def _calculate_totals(self):
		self.total_amount = sum((item.amount or 0) for item in self.items)
		if (self.status or "Pending") == "Paid":
			self.outstanding_amount = 0
		else:
			self.outstanding_amount = self.total_amount

	def _ensure_alignment_with_sales_order(self):
		sales_order = frappe.get_doc("Sales Order", self.sales_order)
		expected_type = "Cash" if sales_order.sales_type == "Cash" else "Credit"
		if not self.invoice_type:
			self.invoice_type = expected_type
		if self.invoice_type != expected_type:
			frappe.throw(_("Invoice type must match the sales order sales type ({0}).").format(expected_type))

		outstanding_capacity = sales_order.get_outstanding_amount(exclude_invoice=self.name if self.name else None)
		if self.docstatus == 1:
			# When updating an already submitted invoice (rare), include its current total
			outstanding_capacity += flt(self.total_amount or 0)

		if flt(self.total_amount) - outstanding_capacity > 0.01:
			frappe.throw(
				_("Invoice value exceeds the remaining amount for this sales order ({0}).").format(
					frappe.utils.fmt_money(outstanding_capacity, currency=sales_order.currency)
				)
			)

	def _sync_sales_order_progress(self):
		if not self.sales_order:
			return
		sales_order = frappe.get_doc("Sales Order", self.sales_order)
		sales_order.update_invoicing_progress()
		if flt(sales_order.outstanding_amount) <= PAYMENT_TOLERANCE:
			sales_order._finalize_reservations()

	def _maybe_create_gate_pass(self):
		if not self.sales_order:
			return
		if self.gate_pass:
			return
		sales_order = frappe.get_doc("Sales Order", self.sales_order)
		# Auto-create for both credit and cash invoices; allow partial for cash or credit
		gate_pass = sales_order.create_gate_pass(allow_partial=True)
		self.gate_pass = gate_pass.name
		self.db_set("gate_pass", gate_pass.name, update_modified=False)
