import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

VAT_RATE = 0.15


class ProformaInvoice(Document):
	"""Customer quotation that can be converted into a Sales Order."""

	def validate(self):
		self._set_defaults()
		self._set_item_defaults()
		self._calculate_totals()

	def on_submit(self):
		self.status = "Submitted"
		self.db_set("status", "Submitted")

	def on_cancel(self):
		self.status = "Cancelled"
		self.db_set("status", "Cancelled")

	def create_sales_order(self):
		if self.docstatus != 1:
			frappe.throw(_("Submit the proforma invoice before creating a sales order."))
		if self.status == "Converted":
			frappe.throw(_("This proforma invoice is already converted."))

		sales_order = frappe.new_doc("Sales Order")
		sales_order.customer = self.customer
		sales_order.sales_type = self.sales_type or "Cash"
		sales_order.currency = self.currency or frappe.db.get_default("currency") or "ETB"
		sales_order.order_date = nowdate()
		if hasattr(sales_order, "proforma_invoice"):
			sales_order.proforma_invoice = self.name

		for item in self.items:
			sales_order.append(
				"items",
				{
					"product": item.product,
					"product_name": item.product_name,
					"description": item.description,
					"quantity": item.quantity,
					"uom": item.uom,
					"rate": flt(item.rate or 0) * (1 + VAT_RATE),
				},
			)

		if not sales_order.items:
			frappe.throw(_("Cannot create a sales order without items."))

		sales_order.insert(ignore_permissions=True)
		self.status = "Converted"
		self.db_set({"status": "Converted"})

		return sales_order

	def _set_defaults(self):
		if self.docstatus == 0 and not self.status:
			self.status = "Draft"
		if not self.currency:
			self.currency = frappe.db.get_default("currency") or "ETB"

	def _set_item_defaults(self):
		for item in self.items:
			if item.product and not item.product_name:
				item.product_name = frappe.db.get_value("Product", item.product, "product_name")
			if item.product and not item.uom:
				item.uom = frappe.db.get_value("Product", item.product, "uom")

			quantity = flt(item.quantity or 0)
			rate = flt(item.rate or 0)
			base_amount = quantity * rate
			vat_total = base_amount * VAT_RATE
			gross_amount = base_amount + vat_total

			item.amount = flt(base_amount, item.precision("amount") or None)
			item.price_with_vat = flt(vat_total, item.precision("price_with_vat") or None)
			item.gross_amount = flt(gross_amount, item.precision("gross_amount") or None)

	def _calculate_totals(self):
		self.total_quantity = sum((item.quantity or 0) for item in self.items)
		self.total_amount = sum((item.amount or 0) for item in self.items)
		self.total_vat = sum((item.price_with_vat or 0) for item in self.items)
		self.total_gross_amount = sum((item.gross_amount or 0) for item in self.items)


@frappe.whitelist()
def create_sales_order(proforma_invoice: str):
	doc = frappe.get_doc("Proforma Invoice", proforma_invoice)
	doc.check_permission("submit")
	return doc.create_sales_order().as_dict()
