import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

QTY_TOLERANCE = 0.0001


class PurchaseOrder(Document):
	"""Upstream commercial agreement preceding import shipments."""

	def validate(self):
		self._set_defaults()
		self._calculate_totals()

	def on_submit(self):
		self.status = "Submitted"
		self.db_set("status", "Submitted")

	def on_cancel(self):
		self.status = "Cancelled"
		self.db_set("status", "Cancelled")

	def update_receipt_status(self):
		if self.docstatus != 1:
			return

		fully_received = True
		any_received = False
		for item in self.items:
			received = flt(item.received_qty or 0)
			ordered = flt(item.quantity or 0)
			if received > QTY_TOLERANCE:
				any_received = True
			if ordered - received > QTY_TOLERANCE:
				fully_received = False

		target_status = "Submitted"
		if fully_received and any_received:
			target_status = "Closed"
		elif any_received:
			target_status = "Partially Received"

		if self.status != target_status:
			self.db_set("status", target_status, update_modified=False)
			self.status = target_status

	def _set_defaults(self):
		if self.docstatus == 0 and not self.status:
			self.status = "Draft"

		if not self.purchase_currency:
			# Ensure purchase currency is set before child rows rely on it for currency formatting
			self.purchase_currency = frappe.db.get_default("currency") or self.local_currency

		if not self.local_currency:
			self.local_currency = frappe.db.get_default("currency") or self.purchase_currency

		if self.purchase_currency == self.local_currency or not self.purchase_currency:
			if not self.purchase_exchange_rate:
				self.purchase_exchange_rate = 1
		else:
			if flt(self.purchase_exchange_rate or 0) <= 0:
				frappe.throw(
					_("Set a positive exchange rate to convert {0} to {1}.").format(self.purchase_currency, self.local_currency)
				)

		for item in self.items:
			if item.product and not item.product_name:
				item.product_name = frappe.db.get_value("Product", item.product, "product_name")
			if item.product and not item.uom:
				item.uom = frappe.db.get_value("Product", item.product, "uom")
			# Ensure child rows always carry the purchase currency so Currency fields format correctly
			item.purchase_currency = self.purchase_currency
			qty = flt(item.quantity or 0)
			rate = flt(item.rate or 0)
			item.amount = qty * rate
			if not item.required_by and getattr(self, "expected_shipment", None):
				item.required_by = self.expected_shipment

	def _calculate_totals(self):
		self.total_quantity = sum(flt(item.quantity or 0) for item in self.items)
		self.total_amount = sum(flt(item.amount or 0) for item in self.items)
		rate = flt(self.purchase_exchange_rate or 0)
		if self.purchase_currency == self.local_currency:
			self.total_amount_local = self.total_amount
		elif rate > 0:
			self.total_amount_local = flt(self.total_amount) * rate
		else:
			self.total_amount_local = 0


@frappe.whitelist()
def create_import_shipment(purchase_order: str):
	po = frappe.get_doc("Purchase Order", purchase_order)
	po.check_permission("submit")
	if po.docstatus != 1:
		frappe.throw(_("Submit the purchase order before creating an import shipment."))

	shipment = frappe.new_doc("Import Shipment")
	shipment.purchase_order = po.name
	shipment.import_reference = po.name
	shipment.supplier = po.supplier
	shipment.incoterm = po.incoterm
	shipment.arrival_date = po.expected_shipment
	shipment.expected_arrival = po.expected_shipment
	shipment.currency = po.purchase_currency
	shipment.local_currency = po.local_currency
	shipment.shipment_date = po.po_date

	for item in po.items:
		pending_qty = flt(item.quantity or 0) - flt(item.received_qty or 0)
		if pending_qty <= QTY_TOLERANCE:
			continue
		shipment.append(
			"items",
			{
				"product": item.product,
				"product_name": item.product_name,
				"description": item.description,
				"quantity": pending_qty,
				"uom": item.uom,
				"base_rate": item.rate,
				"purchase_order_item": item.name,
			},
		)

	if not shipment.items:
		frappe.throw(_("All items on Purchase Order {0} are fully received.").format(po.name))

	shipment.insert(ignore_permissions=True)
	return shipment.as_dict()


def get_dashboard_data():
	return {
		"fieldname": "purchase_order",
		"transactions": [
			{"label": _("Fulfilment"), "items": ["Import Shipment", "Landing Cost Worksheet"]},
		],
		"non_standard_fieldnames": {
			"Landing Cost Worksheet": "purchase_order",
		},
		"internal_links": {
			"Supplier": ["supplier"],
		},
	}
