import frappe
from frappe.model.document import Document


class PushSubscription(Document):
	"""Stores browser push subscription for a user."""

	def validate(self):
		if not self.user:
			self.user = frappe.session.user
