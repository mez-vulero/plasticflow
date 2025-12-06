import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import nowdate


class LoadingOrder(Document):
	"""Represents a loading task for a Sales Order."""

	def validate(self):
		if not self.loading_date:
			self.loading_date = nowdate()
		self._sync_customer_and_shipment()
		self._set_item_defaults()
		self._ensure_gate_pass_request()

	def _sync_customer_and_shipment(self):
		if not self.sales_order or not frappe.db.exists("Sales Order", self.sales_order):
			return
		so = frappe.get_cached_doc("Sales Order", self.sales_order)
		self.customer = so.customer
		if so.import_shipment:
			self.import_shipment = so.import_shipment

	def _set_item_defaults(self):
		for row in self.items:
			if row.product and not row.product_name:
				row.product_name = frappe.db.get_value("Product", row.product, "product_name")

	def _ensure_gate_pass_request(self):
		if self.status != "Completed":
			return
		if self.gate_pass_request and frappe.db.exists("Gate Pass Request", self.gate_pass_request):
			return

		gpr = frappe.new_doc("Gate Pass Request")
		gpr.sales_order = self.sales_order
		gpr.loading_order = self.name
		gpr.status = "Pending"
		gpr.insert(ignore_permissions=True)
		self.gate_pass_request = gpr.name
		if self.sales_order and frappe.db.exists("Sales Order", self.sales_order):
			frappe.db.set_value("Sales Order", self.sales_order, "gate_pass", gpr.name, update_modified=False)
		frappe.msgprint(
			_("Gate Pass Request {0} created.").format(gpr.name),
			indicator="green",
			alert=True,
		)


@frappe.whitelist()
def create_loading_order(sales_order: str):
	if not sales_order:
		frappe.throw(_("Sales Order is required."))
	so = frappe.get_doc("Sales Order", sales_order)
	if so.docstatus != 1:
		frappe.throw(_("Submit the Sales Order before creating a Loading Order."))

	doc = frappe.new_doc("Loading Order")
	doc.sales_order = so.name
	doc.customer = so.customer
	doc.import_shipment = so.import_shipment
	doc.loading_date = nowdate()
	doc.status = "New Order"

	for item in so.items:
		doc.append(
			"items",
			{
				"product": item.product,
				"product_name": item.product_name,
				"quantity": item.quantity,
				"uom": item.uom,
				"import_shipment_item": item.import_shipment_item,
			},
		)

	doc.insert(ignore_permissions=True)
	return {"name": doc.name, "doctype": doc.doctype}
