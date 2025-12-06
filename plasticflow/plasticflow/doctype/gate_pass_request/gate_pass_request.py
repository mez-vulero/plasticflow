import frappe
from frappe import _
from frappe.model.document import Document


APPROVER_ROLES = {"Finance Officer", "Sales Manager", "System Manager"}
DISPATCHER_ROLES = {"Store Manager", "System Manager"}


class GatePassRequest(Document):
	"""Gate Pass approval request raised from Loading Orders."""

	def validate(self):
		if self.name and not self.gate_pass:
			self.gate_pass = self.name
		if self.status == "Approved":
			self._ensure_approver_role()
		if self.status == "Dispatched":
			self._ensure_dispatch_rules()
			if not self.dispatched_on:
				self.dispatched_on = frappe.utils.now_datetime()

	def _ensure_approver_role(self):
		if frappe.session.user == "Administrator":
			return
		user_roles = set(frappe.get_roles(frappe.session.user))
		if not (user_roles & APPROVER_ROLES):
			frappe.throw(
				_("Only Finance Officer or Sales Manager can approve a Gate Pass Request."),
				title=_("Not Permitted"),
			)

	def _ensure_dispatch_rules(self):
		previous = self.get_doc_before_save()
		prev_status = previous.status if previous else None
		if prev_status != "Approved":
			frappe.throw(_("Gate Pass Request must be approved before it can be dispatched."))

		if frappe.session.user == "Administrator":
			return
		user_roles = set(frappe.get_roles(frappe.session.user))
		if not (user_roles & DISPATCHER_ROLES):
			frappe.throw(_("Only Store Manager can mark Gate Pass Request as Dispatched."), title=_("Not Permitted"))
