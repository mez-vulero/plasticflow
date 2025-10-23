import frappe
from frappe.model.document import Document
from frappe.utils import nowdate


class PlasticflowInvoice(Document):
	"""Finance invoice generated after payment verification."""

	def validate(self):
		self._set_item_defaults()
		self._calculate_totals()
		if not self.due_date:
			self.due_date = self.invoice_date or nowdate()

	def on_submit(self):
		gate_pass = self._create_gate_pass()
		self.db_set("gate_pass", gate_pass.name)
		frappe.db.set_value("Sales Order", self.sales_order, {"status": "Ready for Delivery", "gate_pass": gate_pass.name})

	def on_cancel(self):
		if self.gate_pass:
			frappe.db.set_value("Gate Pass", self.gate_pass, "status", "Cancelled")
		frappe.db.set_value("Sales Order", self.sales_order, {"status": "Cancelled"})

	def _set_item_defaults(self):
		for item in self.items:
			if item.product and not item.product_name:
				item.product_name = frappe.db.get_value("Product", item.product, "product_name")
			if item.quantity and item.rate:
				item.amount = (item.quantity or 0) * (item.rate or 0)

	def _calculate_totals(self):
		self.total_amount = sum((item.amount or 0) for item in self.items)
		if self.payment_status == "Paid":
			self.outstanding_amount = 0
		else:
			self.outstanding_amount = self.total_amount

	def _create_gate_pass(self):
		sales_order = frappe.get_doc("Sales Order", self.sales_order)
		gate_pass = frappe.new_doc("Gate Pass")
		gate_pass.invoice = self.name
		gate_pass.sales_order = self.sales_order
		gate_pass.warehouse = self._guess_warehouse(sales_order)
		gate_pass.gate_pass_date = nowdate()
		gate_pass.status = "Pending"

		for item in sales_order.items:
			gate_pass.append(
				"items",
				{
					"product": item.product,
					"product_name": item.product_name,
					"quantity": item.quantity,
					"uom": item.uom,
					"stock_batch_item": item.batch_item,
					"warehouse": item.warehouse or gate_pass.warehouse,
				},
			)

		gate_pass.insert(ignore_permissions=True)
		return gate_pass

	def _guess_warehouse(self, sales_order):
		for item in sales_order.items:
			if item.warehouse:
				return item.warehouse
			if item.batch_item:
				parent = frappe.db.get_value("Stock Batch Item", item.batch_item, "parent")
				if parent:
					return frappe.db.get_value("Stock Batch", parent, "warehouse")
		return None
