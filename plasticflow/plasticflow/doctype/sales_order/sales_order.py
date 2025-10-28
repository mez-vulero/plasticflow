import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

from plasticflow.stock import ledger as stock_ledger

PAYMENT_TOLERANCE = 0.01
QTY_TOLERANCE = 0.0001


class SalesOrder(Document):
	"""Coordinates the commercial process from order capture to delivery."""

	def validate(self):
		self._set_item_defaults()
		self._calculate_totals()
		self._sync_payment_tracking()
		self._set_invoice_progress_fields()

	def before_submit(self):
		reservations = self._collect_batch_reservations()
		self._validate_stock_availability(reservations)
		if self.delivery_source == "Warehouse":
			self._enforce_fifo(reservations)

		if self.sales_type == "Cash":
			self.status = "Payment Pending"
			self.payment_status = "Payment Pending"
		else:
			self.status = "Credit Sales"
			self.payment_status = "Draft"

	def on_submit(self):
		reservations = self._collect_batch_reservations()
		self._apply_reservations(reservations)
		self.db_set(
			{
				"status": self.status,
				"payment_status": self.payment_status,
			}
		)
		self.update_invoicing_progress()

	def on_update_after_submit(self):
		self.update_invoicing_progress()

	def on_cancel(self):
		reservations = self._collect_batch_reservations()
		self._release_reservations(reservations)
		self.db_set(
			{
				"status": "Cancelled",
				"payment_status": "Payment Failed" if self.sales_type == "Cash" else "Draft",
			}
		)

	def _set_item_defaults(self):
		for item in self.items:
			if item.product and not item.product_name:
				item.product_name = frappe.db.get_value("Product", item.product, "product_name")
			if item.product and not item.uom:
				item.uom = frappe.db.get_value("Product", item.product, "uom")
			if item.quantity and item.rate:
				item.amount = (item.quantity or 0) * (item.rate or 0)

	def _calculate_totals(self):
		self.total_quantity = sum((item.quantity or 0) for item in self.items)
		self.total_amount = sum((item.amount or 0) for item in self.items)

	def _set_invoice_progress_fields(self):
		total_invoiced = self._get_total_invoiced_amount()
		self.invoiced_amount = total_invoiced
		self.outstanding_amount = max(flt(self.total_amount) - total_invoiced, 0)

	def _sync_payment_tracking(self):
		# Skip enforcement while draft
		if self.docstatus == 0:
			return

		if self.sales_type == "Credit":
			self.payment_status = "Draft"
			if self.status not in {"Invoiced", "Ready for Delivery", "Completed"}:
				self.status = "Credit Sales"
			return

		total_amount = flt(self.total_amount or 0)
		total_paid = self._sum_payment_slips()
		has_slip = bool(self.payment_slips)

		if total_paid - total_amount > PAYMENT_TOLERANCE:
			frappe.throw(
				_("Total payment {0} cannot exceed sales order total {1}.").format(
					frappe.utils.fmt_money(total_paid, currency=self.currency),
					frappe.utils.fmt_money(total_amount, currency=self.currency),
				)
			)

		if self.payment_status == "Payment Verified" and not has_slip:
			frappe.throw(_("Attach at least one payment slip before marking the payment as verified."))
		if self.payment_status == "Payment Verified" and abs(total_paid - total_amount) > PAYMENT_TOLERANCE:
			frappe.throw(_("Amount paid on the slips must match the sales order total before verifying payment."))

		if total_amount <= PAYMENT_TOLERANCE:
			self.payment_status = "Payment Verified"
			if self.status in {"Draft", "Payment Pending", "Payment Verified"}:
				self.status = "Payment Verified"
			return

		if abs(total_paid - total_amount) <= PAYMENT_TOLERANCE and has_slip:
			self.payment_status = "Payment Verified"
			if self.status in {"Draft", "Payment Pending", "Payment Verified"}:
				self.status = "Payment Verified"
		else:
			if self.status in {"Draft", "Payment Pending", "Payment Verified"}:
				self.status = "Payment Pending"
			if self.payment_status != "Payment Pending":
				self.payment_status = "Payment Pending"

	def _sum_payment_slips(self):
		return sum(flt(row.amount_paid or 0) for row in self.payment_slips)

	def _collect_batch_reservations(self):
		reservations = {}
		for item in self.items:
			if not item.batch_item:
				continue
			child = frappe.get_doc("Plasticflow Stock Entry Item", item.batch_item)
			parent = frappe.get_doc("Plasticflow Stock Entry", child.parent)
			entry = reservations.setdefault(
				child.parent,
				{"rows": [], "from_customs": parent.status == "At Customs"},
			)
			entry["from_customs"] = parent.status == "At Customs"
			entry["rows"].append(
				{
					"child_name": child.name,
					"qty": item.quantity or 0,
				}
			)
		return reservations

	def _collect_location_requirements(self):
		location_type = "Customs" if self.delivery_source == "Direct from Customs" else "Warehouse"
		requirements = {}
		for item in self.items:
			required = flt(item.quantity or 0)
			if required <= 0:
				continue
			key = (item.product, location_type)
			requirements[key] = requirements.get(key, 0) + required
		return requirements

	def _validate_stock_availability(self, reservations):
		for (product, location_type), required_qty in self._collect_location_requirements().items():
			available_qty = stock_ledger.get_available_quantity(product, location_type=location_type)
			if required_qty - available_qty > QTY_TOLERANCE:
				frappe.throw(
					_("Insufficient {0} stock for {1}. Required {2}, available {3}.").format(
						location_type.lower(),
						product,
						frappe.utils.fmt_float(required_qty),
						frappe.utils.fmt_float(available_qty),
					)
				)

		for batch_name, payload in reservations.items():
			batch = frappe.get_doc("Plasticflow Stock Entry", batch_name)
			for entry in payload["rows"]:
				child = next((row for row in batch.items if row.name == entry["child_name"]), None)
				if not child:
					frappe.throw(_("Unable to locate batch item for reservation."))
				available = (child.received_qty or 0) - (child.reserved_qty or 0) - (child.issued_qty or 0)
				if entry["qty"] > available:
					frappe.throw(
						_("Not enough available quantity in batch {0} for {1}. Requested {2}, available {3}.").format(
							batch.name,
							child.product,
							entry["qty"],
							available,
						)
					)

	def _apply_reservations(self, reservations):
		for batch_name, payload in reservations.items():
			batch = frappe.get_doc("Plasticflow Stock Entry", batch_name)
			updated = False
			for entry in payload["rows"]:
				child = next((row for row in batch.items if row.name == entry["child_name"]), None)
				if not child:
					continue
				child.reserved_qty = (child.reserved_qty or 0) + (entry["qty"] or 0)
				updated = True
				stock_ledger.adjust_for_reservation(child, entry["qty"], from_customs=payload["from_customs"])
			if updated:
				batch.save(ignore_permissions=True)

	def _release_reservations(self, reservations):
		for batch_name, payload in reservations.items():
			batch = frappe.get_doc("Plasticflow Stock Entry", batch_name)
			updated = False
			for entry in payload["rows"]:
				child = next((row for row in batch.items if row.name == entry["child_name"]), None)
				if not child:
					continue
				child.reserved_qty = max((child.reserved_qty or 0) - (entry["qty"] or 0), 0)
				updated = True
				stock_ledger.release_reservation(child, entry["qty"], from_customs=payload["from_customs"])
			if updated:
				batch.save(ignore_permissions=True)

	def _enforce_fifo(self, reservations):
		for batch_name, payload in reservations.items():
			if payload["from_customs"]:
				continue
			batch = frappe.get_doc("Plasticflow Stock Entry", batch_name)
			for entry in payload["rows"]:
				child = next((row for row in batch.items if row.name == entry["child_name"]), None)
				if not child:
					continue
				arrival_marker = batch.arrival_date or batch.creation
				available_older = frappe.db.sql(
					"""
					select sei.name
					from `tabPlasticflow Stock Entry Item` sei
					inner join `tabPlasticflow Stock Entry` se on se.name = sei.parent
					where se.warehouse = %s
					and sei.product = %s
					and se.status = 'Available'
					and (
						coalesce(se.arrival_date, se.creation) < %s
						or (
							coalesce(se.arrival_date, se.creation) = %s
							and se.creation < %s
						)
					)
					and (sei.received_qty - sei.reserved_qty - sei.issued_qty) > 0
					limit 1
					""",
					(batch.warehouse, child.product, arrival_marker, arrival_marker, batch.creation),
				)
				if available_older:
					frappe.throw(
						_("FIFO policy violation for {0}. Older stock is available in warehouse {1}.").format(
							child.product, batch.warehouse
						)
					)

	def _get_total_invoiced_amount(self, exclude=None):
		if self.is_new():
			return 0.0
		params = [self.name]
		exclude_clause = ""
		if exclude:
			exclude_clause = "and name != %s"
			params.append(exclude)
		result = frappe.db.sql(
			f"""
			select coalesce(sum(total_amount), 0)
			from `tabPlasticflow Invoice`
			where sales_order = %s
			and docstatus = 1
			{exclude_clause}
			""",
			tuple(params),
		)
		return flt(result[0][0] if result else 0.0)

	def _get_latest_invoice_name(self):
		if self.is_new():
			return None
		row = frappe.db.sql(
			"""
			select name
			from `tabPlasticflow Invoice`
			where sales_order = %s and docstatus = 1
			order by modified desc
			limit 1
			""",
			(self.name,),
		)
		return row[0][0] if row else None

	def get_outstanding_amount(self, exclude_invoice=None):
		total_invoiced = self._get_total_invoiced_amount(exclude=exclude_invoice)
		return max(flt(self.total_amount) - total_invoiced, 0)

	def update_invoicing_progress(self):
		if self.is_new():
			return

		total_invoiced = self._get_total_invoiced_amount()
		outstanding = max(flt(self.total_amount) - total_invoiced, 0)
		latest_invoice = self._get_latest_invoice_name()

		updates = {
			"invoiced_amount": total_invoiced,
			"outstanding_amount": outstanding,
			"invoice": latest_invoice,
		}

		if self.docstatus == 1:
			if outstanding <= PAYMENT_TOLERANCE:
				if self.status not in {"Ready for Delivery", "Completed"}:
					updates["status"] = "Invoiced"
					self.status = "Invoiced"
			else:
				if self.sales_type == "Cash":
					target_status = "Payment Verified" if self.payment_status == "Payment Verified" else "Payment Pending"
				else:
					target_status = "Credit Sales"
				if self.status == "Ready for Delivery":
					updates["gate_pass"] = None
				if self.status != "Completed":
					updates["status"] = target_status
					self.status = target_status

		frappe.db.set_value("Sales Order", self.name, updates, update_modified=False)
		self.invoiced_amount = total_invoiced
		self.outstanding_amount = outstanding
		self.invoice = latest_invoice
		if "gate_pass" in updates:
			self.gate_pass = updates["gate_pass"]

	def create_invoice(self, invoice_amount=None):
		if self.docstatus != 1:
			frappe.throw(_("Submit the sales order before creating invoices."))

		outstanding = self.get_outstanding_amount()
		if outstanding <= PAYMENT_TOLERANCE:
			frappe.throw(_("This sales order is already fully invoiced."))

		amount = outstanding if invoice_amount is None else flt(invoice_amount)
		if amount <= 0:
			frappe.throw(_("Invoice amount must be greater than zero."))
		if amount - outstanding > PAYMENT_TOLERANCE:
			frappe.throw(
				_("Invoice amount cannot exceed the outstanding amount ({0}).").format(
					frappe.utils.fmt_money(outstanding, currency=self.currency)
				)
			)

		invoice = self._build_invoice_doc(amount)
		invoice.insert(ignore_permissions=True)
		self.update_invoicing_progress()
		return invoice

	def _build_invoice_doc(self, amount):
		invoice = frappe.new_doc("Plasticflow Invoice")
		invoice.sales_order = self.name
		invoice.customer = self.customer
		invoice.currency = self.currency
		invoice.invoice_date = nowdate()
		invoice.invoice_type = "Cash" if self.sales_type == "Cash" else "Credit"
		invoice.payment_status = "Pending"

		total_amount = flt(self.total_amount)
		ratio = 1 if total_amount <= PAYMENT_TOLERANCE else min(1, flt(amount) / total_amount)

		last_item = None
		for item in self.items:
			base_qty = flt(item.quantity or 0)
			if base_qty <= 0:
				continue
			qty = base_qty * ratio
			if qty <= 0:
				continue
			rate = flt(item.rate or 0)
			invoice_item = invoice.append(
				"items",
				{
					"product": item.product,
					"product_name": item.product_name,
					"description": item.description,
					"quantity": qty,
					"uom": item.uom,
					"rate": rate,
				},
			)
			invoice_item.amount = flt(invoice_item.quantity or 0) * rate
			last_item = invoice_item

		if not invoice.items:
			frappe.throw(_("Unable to prepare invoice items. Ensure the sales order has quantities and rates."))

		# Adjust final line for rounding differences
		for row in invoice.items:
			row.amount = flt(row.quantity or 0) * flt(row.rate or 0)
		invoice.total_amount = sum(flt(row.amount or 0) for row in invoice.items)

		difference = flt(amount) - flt(invoice.total_amount)
		if abs(difference) > PAYMENT_TOLERANCE and last_item:
			rate = flt(last_item.rate or 0)
			qty = flt(last_item.quantity or 0)
			if rate:
				last_item.quantity = qty + difference / rate
			elif qty:
				last_item.rate = (flt(last_item.amount or 0) + difference) / qty
			last_item.amount = flt(last_item.quantity or 0) * flt(last_item.rate or 0)
			invoice.total_amount = sum(flt(row.amount or 0) for row in invoice.items)

		if abs(flt(amount) - flt(invoice.total_amount)) > PAYMENT_TOLERANCE:
			frappe.throw(_("Unable to allocate invoice items for the requested amount. Please create the invoice manually."))

		invoice.outstanding_amount = invoice.total_amount
		return invoice

	def create_gate_pass(self):
		if self.docstatus != 1:
			frappe.throw(_("Submit the sales order before generating a gate pass."))

		outstanding = self.get_outstanding_amount()
		if outstanding > PAYMENT_TOLERANCE:
			frappe.throw(
				_("Invoice the full value before generating a gate pass. Outstanding amount: {0}").format(
					frappe.utils.fmt_money(outstanding, currency=self.currency)
				)
			)

		if self.gate_pass and frappe.db.exists("Gate Pass", self.gate_pass):
			return frappe.get_doc("Gate Pass", self.gate_pass)

		latest_invoice = self._get_latest_invoice_name()
		if not latest_invoice:
			frappe.throw(_("Submit at least one invoice before generating the gate pass."))

		gate_pass = self._build_gate_pass_doc(latest_invoice)
		gate_pass.insert(ignore_permissions=True)
		frappe.db.set_value("Plasticflow Invoice", latest_invoice, "gate_pass", gate_pass.name, update_modified=False)
		self.db_set({"gate_pass": gate_pass.name, "status": "Ready for Delivery"})
		return gate_pass

	def _build_gate_pass_doc(self, invoice_name):
		gate_pass = frappe.new_doc("Gate Pass")
		gate_pass.invoice = invoice_name
		gate_pass.sales_order = self.name
		gate_pass.warehouse = None
		gate_pass.gate_pass_date = nowdate()
		gate_pass.status = "Pending"

		for item in self.items:
			gate_pass.append(
				"items",
				{
					"product": item.product,
					"product_name": item.product_name,
					"quantity": item.quantity,
					"uom": item.uom,
					"stock_entry_item": item.batch_item,
					"warehouse": item.warehouse,
				},
			)
		return gate_pass


@frappe.whitelist()
def create_sales_invoice(sales_order, amount=None):
	so = frappe.get_doc("Sales Order", sales_order)
	so.check_permission("submit")
	invoice = so.create_invoice(invoice_amount=amount)
	return invoice.as_dict()


@frappe.whitelist()
def create_sales_order_gate_pass(sales_order):
	so = frappe.get_doc("Sales Order", sales_order)
	so.check_permission("submit")
	gate_pass = so.create_gate_pass()
	return gate_pass.as_dict()
