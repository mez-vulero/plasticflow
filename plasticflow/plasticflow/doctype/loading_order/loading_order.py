import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime, nowdate


class LoadingOrder(Document):
	"""Represents a loading task for a Sales Order."""

	def validate(self):
		if not self.loading_date:
			self.loading_date = nowdate()
		self._sync_customer_and_shipment()
		self._set_item_defaults()
		self._ensure_gate_pass()

	def _sync_customer_and_shipment(self):
		if not self.sales_order or not frappe.db.exists("Sales Order", self.sales_order):
			return
		so = frappe.get_cached_doc("Sales Order", self.sales_order)
		self.customer = so.customer
		if not self.destination:
			self.destination = so.customer
		if so.driver_name and not self.driver_name:
			self.driver_name = so.driver_name
		if so.plate_number and not self.vehicle_plate:
			self.vehicle_plate = so.plate_number
		if so.driver_phone and not self.driver_phone:
			self.driver_phone = so.driver_phone
		if so.import_shipment:
			self.import_shipment = so.import_shipment

	def _set_item_defaults(self):
		for row in self.items:
			if row.product and not row.product_name:
				row.product_name = frappe.db.get_value("Product", row.product, "product_name")

	def _ensure_gate_pass(self):
		if self.status != "Completed":
			return
		so = None
		if self.sales_order and frappe.db.exists("Sales Order", self.sales_order):
			so = frappe.get_cached_doc("Sales Order", self.sales_order)
			if so.gate_pass and frappe.db.exists("Gate Pass", so.gate_pass):
				self.gate_pass_request = so.gate_pass
				return
		if self.gate_pass_request and frappe.db.exists("Gate Pass", self.gate_pass_request):
			return

		gp = frappe.new_doc("Gate Pass")
		gp.sales_order = self.sales_order
		gp.loading_order = self.name
		gp.customer = self.customer or (so.customer if so else None)
		gp.destination = self.destination or (so.customer if so else None)
		gp.driver_name = self.driver_name or (so.driver_name if so else None)
		gp.plate_number = self.vehicle_plate or (so.plate_number if so else None)
		gp.driver_phone = self.driver_phone or (so.driver_phone if so else None)
		gp.generated_on = now_datetime()
		for row in self.items:
			gp.append(
				"items",
				{
					"product": row.product,
					"product_name": row.product_name,
					"quantity": row.quantity,
					"uom": row.uom,
				},
			)
		gp.insert(ignore_permissions=True)
		self.gate_pass_request = gp.name
		if self.sales_order and frappe.db.exists("Sales Order", self.sales_order):
			frappe.db.set_value("Sales Order", self.sales_order, "gate_pass", gp.name, update_modified=False)
		frappe.msgprint(
			_("Gate Pass {0} generated.").format(gp.name),
			indicator="green",
			alert=True,
		)


@frappe.whitelist()
def create_loading_order(sales_order: str):
	if not sales_order:
		frappe.throw(_("Sales Order is required."))
	existing = frappe.db.get_value(
		"Loading Order",
		{"sales_order": sales_order},
		"name",
		order_by="creation desc",
	)
	if existing:
		return {"name": existing, "doctype": "Loading Order"}
	so = frappe.get_doc("Sales Order", sales_order)
	if so.docstatus != 1:
		frappe.throw(_("Submit the Sales Order before creating a Loading Order."))

	doc = frappe.new_doc("Loading Order")
	doc.sales_order = so.name
	doc.customer = so.customer
	doc.destination = so.customer
	doc.import_shipment = so.import_shipment
	doc.loading_date = nowdate()
	doc.status = "New Order"
	doc.driver_name = so.driver_name
	doc.vehicle_plate = so.plate_number
	doc.driver_phone = so.driver_phone

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
