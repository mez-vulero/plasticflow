import frappe
from frappe import _
from frappe.model.document import Document


class Customer(Document):
	"""Customer master for buyers of plastic materials."""

	def validate(self):
		self._validate_tin()

	def _validate_tin(self):
		if not self.tin:
			return
		tin = str(self.tin).strip()
		if len(tin) != 10 or not tin.isdigit():
			frappe.throw(_("TIN must be a 10-digit number."))
		self.tin = tin
