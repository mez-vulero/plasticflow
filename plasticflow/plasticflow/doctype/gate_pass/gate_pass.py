import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class GatePass(Document):
	"""Auto-generated gate pass created from Loading Orders."""

	def validate(self):
		if not self.generated_on:
			self.generated_on = now_datetime()
