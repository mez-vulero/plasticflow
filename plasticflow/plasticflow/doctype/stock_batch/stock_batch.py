from frappe.model.document import Document


class StockBatch(Document):
	"""Represents stock made available after customs clearance."""

	def validate(self):
		self._update_item_balances()
		self._update_totals()
		self._set_status()

	def _update_item_balances(self):
		for item in self.items:
			received = item.received_qty or 0
			reserved = item.reserved_qty or 0
			issued = item.issued_qty or 0
			item.available_qty = max(received - reserved - issued, 0)

	def _update_totals(self):
		self.total_received_qty = sum((item.received_qty or 0) for item in self.items)
		self.total_reserved_qty = sum((item.reserved_qty or 0) for item in self.items)
		self.total_issued_qty = sum((item.issued_qty or 0) for item in self.items)
		self.available_qty = sum((item.available_qty or 0) for item in self.items)

	def _set_status(self):
		if self.available_qty <= 0 and (self.total_issued_qty or 0):
			self.status = "Depleted"
		elif self.available_qty <= 0 and not self.total_issued_qty:
			self.status = "Reserved"
		elif self.total_reserved_qty:
			self.status = "Reserved"
		elif self.available_qty and self.total_issued_qty:
			self.status = "Partially Issued"
		else:
			self.status = "Available"
