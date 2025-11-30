import frappe
from frappe.model.document import Document


class PlasticflowPushSubscription(Document):
	"""Stores browser push subscription for a user."""

	def validate(self):
		if not self.user:
			self.user = frappe.session.user
