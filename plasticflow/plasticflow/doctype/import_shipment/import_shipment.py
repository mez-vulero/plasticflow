import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

QTY_TOLERANCE = 0.0001


class ImportShipment(Document):
	"""Commercial shipment covering purchase, logistics, and landed cost inputs."""

	def validate(self):
		self._populate_from_purchase_order()
		self._set_item_defaults()
		self._calculate_totals()

	def _populate_from_purchase_order(self):
		if not self.purchase_order:
			return

		po = frappe.get_doc("Purchase Order", self.purchase_order)
		if po.docstatus != 1:
			frappe.throw("Submit the linked purchase order before creating a shipment.")
		self._po_exchange_rate = flt(po.purchase_exchange_rate or 0)
		if self.currency and self.currency != po.purchase_currency:
			frappe.throw("Import currency must match the linked purchase order currency.")
		self.currency = po.purchase_currency
		self.local_currency = self.local_currency or po.local_currency
		self.supplier = self.supplier or po.supplier
		self.incoterm = self.incoterm or po.incoterm
		self.purchase_order_no = self.purchase_order_no or po.name
		if not self.import_reference:
			self.import_reference = po.name
		if not self.shipment_date:
			self.shipment_date = po.po_date
		if not self.expected_arrival:
			self.expected_arrival = po.expected_shipment

		if self.items:
			return

		for item in po.items:
			pending_qty = flt(item.quantity or 0) - flt(item.received_qty or 0)
			if pending_qty <= QTY_TOLERANCE:
				continue
			base_rate = flt(item.rate or 0)
			self.append(
				"items",
				{
					"product": item.product,
					"product_name": item.product_name,
					"description": item.description,
					"quantity": pending_qty,
					"uom": item.uom,
					"base_rate": base_rate,
					"purchase_order_item": item.name,
				},
			)

	def _set_item_defaults(self):
		if not self.local_currency:
			self.local_currency = frappe.db.get_default("currency")

		exchange_rate = 1
		if getattr(self, "_po_exchange_rate", None):
			exchange_rate = flt(self._po_exchange_rate or 0)
		elif self.purchase_order:
			exchange_rate = flt(
				frappe.db.get_value("Purchase Order", self.purchase_order, "purchase_exchange_rate") or 0
			)
		if self.currency == self.local_currency:
			exchange_rate = 1

		for item in self.items:
			if item.product and not item.product_name:
				item.product_name = frappe.db.get_value("Product", item.product, "product_name")
			if item.product and not item.uom:
				item.uom = frappe.db.get_value("Product", item.product, "uom")
			quantity = flt(item.quantity or 0)
			base_rate = flt(item.base_rate or 0)
			item.base_amount = quantity * base_rate
			if quantity:
				item.base_rate = base_rate
			if item.landed_cost_amount and quantity:
				item.landed_cost_rate = flt(item.landed_cost_amount) / quantity
			if item.landed_cost_amount_local and quantity:
				item.landed_cost_rate_local = flt(item.landed_cost_amount_local) / quantity
			if exchange_rate > 0:
				item.base_amount_local = flt(item.base_amount) * exchange_rate
			elif self.currency == self.local_currency:
				item.base_amount_local = flt(item.base_amount)
			else:
				item.base_amount_local = 0

	def _calculate_totals(self):
		total_quantity = sum(flt(item.quantity or 0) for item in self.items)
		total_base = sum(flt(item.base_amount or 0) for item in self.items)
		total_landed = sum(flt(item.landed_cost_amount or 0) for item in self.items)
		total_landed_local = sum(flt(item.landed_cost_amount_local or 0) for item in self.items)

		self.total_quantity = total_quantity
		self.total_shipment_amount = total_base
		self.total_landed_cost = total_landed
		self.total_landed_cost_local = total_landed_local
		self.per_unit_landed_cost = flt(total_landed / total_quantity) if total_quantity else 0
		self.per_unit_landed_cost_local = (
			flt(total_landed_local / total_quantity) if total_quantity else 0
		)
		if not self.landing_cost_status:
			self.landing_cost_status = "Draft"


def get_dashboard_data():
	return {
		"fieldname": "import_shipment",
		"transactions": [
			{"label": _("Costing"), "items": ["Landing Cost Worksheet"]},
			{"label": _("Customs & Stock"), "items": ["Customs Entry", "Plasticflow Stock Entry"]},
		],
		"internal_links": {
			"Purchase Order": ["purchase_order"],
		},
	}
