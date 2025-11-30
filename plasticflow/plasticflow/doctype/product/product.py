import frappe
from frappe.model.document import Document


class Product(Document):
	"""Product master for plastic raw materials."""

	def validate(self):
		self.product_name = (self.product_name or "").strip()
		self.item_code = (self.item_code or "").strip()
		if not self.item_code:
			frappe.throw("Item Code is required")
