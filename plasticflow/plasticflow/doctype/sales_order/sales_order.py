import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

from plasticflow.stock import ledger as stock_ledger

PAYMENT_TOLERANCE = 0.01
QTY_TOLERANCE = 0.0001
VAT_RATE = 0.15
WITHHOLDING_RATE_DEFAULT = 3.0


class SalesOrder(Document):
	"""Coordinates the commercial process from order capture to delivery."""

	def validate(self):
		self._set_item_defaults()
		self._calculate_totals()
		self._sync_import_shipment_context()
		self._sync_payment_tracking()
		self._set_invoice_progress_fields()

	def before_save(self):
		# Recompute pricing fields so manual edits reflect in totals
		self._set_item_defaults()
		self._calculate_totals()
		self._set_invoice_progress_fields()
		if self.docstatus == 1:
			self._sync_payment_tracking()

	def before_submit(self):
		self._calculate_totals()
		reservations = self._collect_batch_reservations()
		self._validate_stock_availability(reservations)
		if self.delivery_source == "Warehouse":
			self._enforce_fifo(reservations)

		if self.sales_type == "Cash":
			self.status = "Payment Pending"
		else:
			self.status = "Credit Sales"

	def on_submit(self):
		reservations = self._collect_batch_reservations()
		self._apply_reservations(reservations)
		self.db_set(
			{
				"status": self.status,
			}
		)
		self.update_invoicing_progress()

	def on_update_after_submit(self):
		self._set_item_defaults()
		self._calculate_totals()
		self._sync_payment_tracking()
		self._set_invoice_progress_fields()
		self.update_invoicing_progress()

	def on_cancel(self):
		reservations = self._collect_batch_reservations(for_release=True)
		self._release_reservations(reservations)
		self.db_set(
			{
				"status": "Cancelled",
			}
		)
		self._clear_links()

	def _set_item_defaults(self):
		parent_withholding = flt(self.withholding_rate or WITHHOLDING_RATE_DEFAULT)
		parent_commission = flt(self.broker_commission_rate or 0)
		detected_shipments: set[str] = set()

		for item in self.items:
			if item.product and not item.product_name:
				item.product_name = frappe.db.get_value("Product", item.product, "product_name")
			if item.product and not item.uom:
				item.uom = frappe.db.get_value("Product", item.product, "uom")

			quantity = flt(item.quantity or 0)
			rate = flt(item.rate or 0)
			item.amount = quantity * rate

			# VAT amount per line (field now represents total VAT for the row)
			vat_total = flt(item.amount * VAT_RATE, item.precision("price_with_vat") or None)
			item.price_with_vat = vat_total
			gross_amount = item.amount + vat_total
			item.gross_amount = gross_amount
			base_amount = item.amount

			item.withholding_rate = parent_withholding
			withholding_rate = parent_withholding
			item.withholding_amount = base_amount * (withholding_rate / 100) if base_amount else 0
			item.net_amount = gross_amount - flt(item.withholding_amount or 0)

			item.commission_rate = parent_commission
			commission_rate = parent_commission
			item.commission_amount = gross_amount * (commission_rate / 100) if gross_amount else 0

			if item.batch_item:
				try:
					stock_item = frappe.get_cached_doc("Stock Entry Items", item.batch_item)
				except frappe.DoesNotExistError:
					stock_item = None
				if stock_item:
					if stock_item.get("import_shipment_item") and not item.import_shipment_item:
						item.import_shipment_item = stock_item.import_shipment_item
					parent_shipment = None
					if item.import_shipment_item:
						parent_shipment = frappe.db.get_value(
							"Import Shipment Item",
							item.import_shipment_item,
							"parent",
						)
					if not parent_shipment:
						parent_shipment = frappe.db.get_value(
							"Stock Entries",
							stock_item.parent,
							"import_shipment",
						)
					if parent_shipment:
						detected_shipments.add(parent_shipment)

		self._pending_import_shipments = detected_shipments

	def _calculate_totals(self):
		self.total_quantity = sum((item.quantity or 0) for item in self.items)
		self.total_amount = sum((item.amount or 0) for item in self.items)
		self.total_gross_amount = sum((item.gross_amount or 0) for item in self.items)
		self.total_withholding = sum((item.withholding_amount or 0) for item in self.items)
		self.total_net_amount = sum((item.net_amount or 0) for item in self.items)
		item_commissions = sum((item.commission_amount or 0) for item in self.items)
		if not item_commissions and flt(self.broker_commission_rate or 0):
			item_commissions = self.total_gross_amount * flt(self.broker_commission_rate or 0) / 100
		self.total_commission = item_commissions
		self._calculate_profitability_fields()

	def _calculate_profitability_fields(self):
		total_landed = 0.0
		rate_cache: dict[object, float] = {}
		for item in self.items:
			quantity = flt(item.quantity or 0)
			if quantity <= 0 or not item.product:
				continue

			landed_rate = 0.0
			if item.import_shipment_item:
				if item.import_shipment_item not in rate_cache:
					rate_cache[item.import_shipment_item] = flt(
						frappe.db.get_value(
							"Import Shipment Item",
							item.import_shipment_item,
							"landed_cost_rate_local",
						)
						or 0
					)
				landed_rate = rate_cache[item.import_shipment_item]
			elif self.import_shipment:
				cache_key = (self.import_shipment, item.product)
				if cache_key not in rate_cache:
					rate_cache[cache_key] = flt(
						frappe.db.get_value(
							"Import Shipment Item",
							{"parent": self.import_shipment, "product": item.product},
							"landed_cost_rate_local",
						)
						or 0
					)
				landed_rate = rate_cache[cache_key]

			total_landed += quantity * landed_rate

		self.landed_cost_total = total_landed
		net_sales = flt(self.total_net_amount or 0)
		commission = flt(self.total_commission or 0)
		profit = net_sales - total_landed - commission
		self.profit_before_tax = profit
		self.margin_percent = (profit / net_sales * 100) if net_sales else 0

	def _sync_import_shipment_context(self):
		pending = set(getattr(self, "_pending_import_shipments", set()) or [])
		if self.import_shipment:
			pending.add(self.import_shipment)
		pending = {name for name in pending if name}
		if len(pending) > 1:
			frappe.throw(
				_("Items reference multiple import shipments. Please split the order per shipment."),
				title=_("Multiple Shipments Detected"),
			)
		if pending:
			self.import_shipment = pending.pop()
		if self.import_shipment:
			for item in self.items:
				if item.import_shipment_item or not item.product:
					continue
				linked_item = frappe.db.get_value(
					"Import Shipment Item",
					{"parent": self.import_shipment, "product": item.product},
					"name",
				)
				if linked_item:
					item.import_shipment_item = linked_item
		if hasattr(self, "_pending_import_shipments"):
			delattr(self, "_pending_import_shipments")

	def _set_invoice_progress_fields(self):
		total_invoiced = self._get_total_invoiced_amount()
		self.invoiced_amount = total_invoiced
		net_receivable = self._net_receivable()
		paid = self._sum_payment_slips(verified_only=self.sales_type == "Cash")
		self.outstanding_amount = max(net_receivable - paid, 0)

	def _sync_payment_tracking(self):
		if self.docstatus == 0:
			return

		expected_payment = self._net_receivable()
		is_cash = self.sales_type == "Cash"
		total_paid = self._sum_payment_slips(verified_only=is_cash)
		has_verified = self._has_verified_payments()

		if not is_cash:
			# Credit sales: skip verification gating, track settlement when fully paid
			if expected_payment <= PAYMENT_TOLERANCE or abs(expected_payment - total_paid) <= PAYMENT_TOLERANCE:
				self.status = "Settled"
			else:
				if self.status not in {"Completed", "Settled"}:
					self.status = "Credit Sales"
			return

		# Cash sales: require at least one verified slip to move forward
		if not has_verified:
			if self.status in {"Draft", "Payment Pending", "Payment Verified", "Settled"}:
				self.status = "Payment Pending"
			return

		if abs(expected_payment - total_paid) <= PAYMENT_TOLERANCE:
			if self.status in {"Draft", "Payment Pending", "Payment Verified"}:
				self.status = "Settled"
			self._maybe_mark_settled(
				total_paid=total_paid,
				expected_payment=expected_payment,
				outstanding=max(expected_payment - total_paid, 0),
			)
		else:
			if self.status in {"Draft", "Payment Pending", "Payment Verified", "Settled"}:
				self.status = "Payment Pending"

	def _sum_payment_slips(self, verified_only: bool = False):
		slip_rows = self.payment_slips or []
		if verified_only:
			slip_rows = [row for row in slip_rows if (row.slip_status or "").lower() == "verified"]
		return sum(flt(row.amount_paid or 0) for row in slip_rows)

	def _maybe_mark_settled(
		self,
		*,
		total_paid: float | None = None,
		expected_payment: float | None = None,
		outstanding: float | None = None,
		total_invoiced: float | None = None,
	) -> bool:
		total_paid = flt(total_paid if total_paid is not None else self._sum_payment_slips())
		expected_payment = flt(expected_payment if expected_payment is not None else self._net_receivable())
		outstanding = flt(outstanding if outstanding is not None else (self.outstanding_amount or 0))
		invoice_target = flt(self.total_gross_amount or self.total_amount or 0)
		invoice_coverage = invoice_target <= PAYMENT_TOLERANCE or (
			total_invoiced is not None and flt(total_invoiced) >= invoice_target - PAYMENT_TOLERANCE
		)

		if not self.payment_slips:
			return False

		if (
			outstanding <= PAYMENT_TOLERANCE
			and abs(total_paid - expected_payment) <= PAYMENT_TOLERANCE
			and invoice_coverage
		):
			self.status = "Settled"
			return True
		return False

	def _net_receivable(self) -> float:
		return flt(self.total_net_amount or self.total_gross_amount or self.total_amount or 0)

	def _has_verified_payments(self) -> bool:
		return any((row.slip_status or "").lower() == "verified" for row in (self.payment_slips or []))

	@staticmethod
	def _ledger_reference(location_type: str, warehouse: str | None = None) -> str:
		return f"{location_type}::{warehouse or 'GLOBAL'}"

	def _gate_pass_dispatched(self) -> bool:
		if not self.gate_pass or not frappe.db.exists("Gate Pass Request", self.gate_pass):
			return False
		return frappe.db.get_value("Gate Pass Request", self.gate_pass, "status") == "Dispatched"

	# Compatibility shim for legacy notifications referencing payment_status
	@property
	def payment_status(self):
		return None

	@payment_status.setter
	def payment_status(self, value):
		# Intentionally ignore to keep status-driven flow
		pass

	def _collect_batch_reservations(self, *, for_release: bool = False):
		reservations: dict[str, dict[str, object]] = {}
		location_type = "Customs" if self.delivery_source == "Direct from Customs" else "Warehouse"
		target_warehouse = self._get_target_warehouse()

		for item in self.items:
			required_qty = flt(item.quantity or 0)
			if required_qty <= 0 or not item.product:
				continue

			if item.batch_item:
				if for_release:
					self._release_specific_batch(reservations, item, required_qty, location_type, target_warehouse)
				else:
					self._reserve_specific_batch(reservations, item, required_qty, location_type, target_warehouse)
				continue

			for batch in self._iter_fifo_batches(
				item.product,
				location_type=location_type,
				warehouse=target_warehouse,
				for_release=for_release,
			):
				batch_qty = flt(batch.reserved_qty if for_release else batch.available_qty or 0)
				if batch_qty <= 0 or required_qty <= 0:
					continue
				allocate = min(required_qty, batch_qty)
				self._add_reservation(
					reservations,
					batch.batch_name,
					batch.child_name,
					allocate,
					from_customs=location_type == "Customs",
				)
				required_qty -= allocate
				if required_qty <= QTY_TOLERANCE:
					break

			if required_qty > QTY_TOLERANCE:
				if for_release:
					frappe.throw(
						_("Insufficient reserved stock to release for {0}. Short by {1} units.").format(
							item.product, f"{required_qty:.3f}"
						)
					)
				frappe.throw(
					_("Insufficient FIFO stock for {0}. Short by {1} units.").format(
						item.product, f"{required_qty:.3f}"
					)
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
		location_type = "Customs" if self.delivery_source == "Direct from Customs" else "Warehouse"
		warehouse = self._get_target_warehouse()
		if not self.import_shipment:
			frappe.throw(_("Import Shipment is required to validate stock for this order."))
		for item in self.items:
			qty = flt(item.quantity or 0)
			if qty <= 0 or not item.product:
				continue
			available_qty = stock_ledger.get_available_quantity_by_shipment(
				item.product,
				location_type=location_type,
				import_shipment=self.import_shipment,
				warehouse=warehouse if location_type == "Warehouse" else None,
			)
			if qty - available_qty > QTY_TOLERANCE:
				frappe.throw(
					_("Insufficient {0} stock for {1}. Required {2}, available {3}.").format(
						location_type.lower(),
						item.product,
						f"{qty:.3f}",
						f"{available_qty:.3f}",
					)
				)

	def _get_target_warehouse(self):
		if self.delivery_source != "Warehouse":
			return None
		for item in self.items:
			if item.warehouse:
				return item.warehouse
		return None

	def _clear_links(self):
		updates = {}
		if self.invoice:
			if frappe.db.exists("Plasticflow Invoice", self.invoice):
				frappe.db.set_value("Plasticflow Invoice", self.invoice, {"sales_order": None}, update_modified=False)
			updates["invoice"] = None
			self.invoice = None
		if self.gate_pass:
			updates["gate_pass"] = None
			self.gate_pass = None
		if self.delivery_note:
			if frappe.db.exists("Delivery Note", self.delivery_note):
				frappe.db.set_value("Delivery Note", self.delivery_note, {"sales_order": None, "gate_pass": None}, update_modified=False)
			updates["delivery_note"] = None
			self.delivery_note = None
		if updates:
			frappe.db.set_value("Sales Order", self.name, updates, update_modified=False)

	def _apply_reservations(self, reservations):
		if reservations:
			for batch_name, payload in reservations.items():
				batch = frappe.get_doc("Stock Entries", batch_name)
				batch.flags.ignore_validate_update_after_submit = True
				updated = False
				for entry in payload["rows"]:
					child = next((row for row in batch.items if row.name == entry["child_name"]), None)
					if not child:
						continue
					child.flags.ignore_validate_update_after_submit = True
					child.reserved_qty = (child.reserved_qty or 0) + (entry["qty"] or 0)
					updated = True
					stock_ledger.adjust_for_reservation(child, entry["qty"], from_customs=payload["from_customs"])
				if updated:
					batch.save(ignore_permissions=True)
			return

		location_type = "Customs" if self.delivery_source == "Direct from Customs" else "Warehouse"
		warehouse = self._get_target_warehouse()
		reference = self._ledger_reference(location_type, warehouse)
		for item in self.items:
			qty = flt(item.quantity or 0)
			if qty <= 0 or not item.product:
				continue
			stock_ledger.apply_delta(
				item.product,
				location_type,
				reference,
				available_delta=-qty,
				reserved_delta=qty,
				warehouse=warehouse if location_type == "Warehouse" else None,
				remarks=f"Reserved for Sales Order {self.name}",
			)

	def _release_reservations(self, reservations):
		if reservations:
			for batch_name, payload in reservations.items():
				batch = frappe.get_doc("Stock Entries", batch_name)
				batch.flags.ignore_validate_update_after_submit = True
				updated = False
				for entry in payload["rows"]:
					child = next((row for row in batch.items if row.name == entry["child_name"]), None)
					if not child:
						continue
					child.flags.ignore_validate_update_after_submit = True
					child.reserved_qty = max((child.reserved_qty or 0) - (entry["qty"] or 0), 0)
					updated = True
					stock_ledger.release_reservation(child, entry["qty"], from_customs=payload["from_customs"])
				if updated:
					batch.save(ignore_permissions=True)
			return

		location_type = "Customs" if self.delivery_source == "Direct from Customs" else "Warehouse"
		warehouse = self._get_target_warehouse()
		reference = self._ledger_reference(location_type, warehouse)
		for item in self.items:
			qty = flt(item.quantity or 0)
			if qty <= 0 or not item.product:
				continue
			stock_ledger.apply_delta(
				item.product,
				location_type,
				reference,
				available_delta=qty,
				reserved_delta=-qty,
				warehouse=warehouse if location_type == "Warehouse" else None,
				remarks=f"Reservation released for Sales Order {self.name}",
			)

	def _finalize_reservations(self):
		"""Convert reserved quantity into issued quantity when billing is complete."""
		location_type = "Customs" if self.delivery_source == "Direct from Customs" else "Warehouse"
		warehouse = self._get_target_warehouse()
		reference = self._ledger_reference(location_type, warehouse)
		for item in self.items:
			qty = flt(item.quantity or 0)
			if qty <= 0 or not item.product:
				continue
			reserved_now = self._get_current_reserved(item.product, location_type, reference, warehouse)
			if reserved_now <= 0:
				continue
			qty_to_convert = min(qty, reserved_now)
			stock_ledger.apply_delta(
				item.product,
				location_type,
				reference,
				reserved_delta=-qty_to_convert,
				issued_delta=qty_to_convert,
				warehouse=warehouse if location_type == "Warehouse" else None,
				remarks=f"Invoiced via Sales Order {self.name}",
			)

	def _restore_reservations(self):
		"""Move issued quantity back to reserved when billing is reversed."""
		location_type = "Customs" if self.delivery_source == "Direct from Customs" else "Warehouse"
		warehouse = self._get_target_warehouse()
		reference = self._ledger_reference(location_type, warehouse)
		for item in self.items:
			qty = flt(item.quantity or 0)
			if qty <= 0 or not item.product:
				continue
			issued_now = self._get_current_issued(item.product, location_type, reference, warehouse)
			if issued_now <= 0:
				continue
			qty_to_restore = min(qty, issued_now)
			stock_ledger.apply_delta(
				item.product,
				location_type,
				reference,
				reserved_delta=qty_to_restore,
				issued_delta=-qty_to_restore,
				warehouse=warehouse if location_type == "Warehouse" else None,
				remarks=f"Invoice reversed for Sales Order {self.name}",
			)

	@staticmethod
	def _get_current_reserved(product, location_type, reference, warehouse):
		filters = {
			"product": product,
			"location_type": location_type,
			"location_reference": reference,
		}
		if warehouse:
			filters["warehouse"] = warehouse
		return flt(frappe.db.get_value("Plasticflow Stock Ledger Entry", filters, "reserved_qty") or 0)

	@staticmethod
	def _get_current_issued(product, location_type, reference, warehouse):
		filters = {
			"product": product,
			"location_type": location_type,
			"location_reference": reference,
		}
		if warehouse:
			filters["warehouse"] = warehouse
		return flt(frappe.db.get_value("Plasticflow Stock Ledger Entry", filters, "issued_qty") or 0)

	def _add_reservation(self, reservations, batch_name, child_name, qty, *, from_customs):
		if qty <= 0:
			return
		entry = reservations.setdefault(batch_name, {"from_customs": from_customs, "rows": []})
		entry["rows"].append({"child_name": child_name, "qty": qty})

	def _reserve_specific_batch(self, reservations, item, required_qty, location_type, target_warehouse):
		row = frappe.db.get_value(
			"Stock Entry Items",
			item.batch_item,
			[
				"name",
				"parent",
				"product",
				"received_qty",
				"reserved_qty",
				"issued_qty",
			],
			as_dict=True,
		)
		if not row:
			frappe.throw(_("Selected batch item {0} not found.").format(item.batch_item))
		if row.product != item.product:
			frappe.throw(_("Batch item {0} does not match product {1}.").format(item.batch_item, item.product))

		parent = frappe.db.get_value(
			"Stock Entries",
			row.parent,
			["status", "warehouse"],
			as_dict=True,
		)
		if not parent:
			frappe.throw(_("Stock Entry {0} linked to batch item {1} not found.").format(row.parent, row.name))

		if location_type == "Warehouse":
			if target_warehouse and parent.warehouse and parent.warehouse != target_warehouse:
				frappe.throw(
					_("Batch {0} is stored in warehouse {1}, not the target warehouse {2}.").format(
						row.parent, parent.warehouse, target_warehouse
					)
				)

		available = flt(row.received_qty or 0) - flt(row.reserved_qty or 0) - flt(row.issued_qty or 0)
		if available + QTY_TOLERANCE < required_qty:
			frappe.throw(
				_("Batch item {0} does not have enough stock. Required {1}, available {2}.").format(
					row.name,
					f"{required_qty:.3f}",
					f"{max(available, 0):.3f}",
				)
			)

		self._add_reservation(
			reservations,
			row.parent,
			row.name,
			required_qty,
			from_customs=location_type == "Customs",
		)

	def _release_specific_batch(self, reservations, item, required_qty, location_type, target_warehouse):
		row = frappe.db.get_value(
			"Stock Entry Items",
			item.batch_item,
			[
				"name",
				"parent",
				"product",
				"reserved_qty",
			],
			as_dict=True,
		)
		if not row:
			frappe.throw(_("Selected batch item {0} not found.").format(item.batch_item))
		if row.product != item.product:
			frappe.throw(_("Batch item {0} does not match product {1}.").format(item.batch_item, item.product))

		parent = frappe.db.get_value(
			"Stock Entries",
			row.parent,
			["status", "warehouse"],
			as_dict=True,
		)
		if not parent:
			frappe.throw(_("Stock Entry {0} linked to batch item {1} not found.").format(row.parent, row.name))

		reserved = flt(row.reserved_qty or 0)
		if reserved + QTY_TOLERANCE < required_qty:
			frappe.throw(
				_("Batch item {0} does not have enough reserved stock to release. Required {1}, reserved {2}.").format(
					row.name,
					f"{required_qty:.3f}",
					f"{max(reserved, 0):.3f}",
				)
			)

		self._add_reservation(
			reservations,
			row.parent,
			row.name,
			required_qty,
			from_customs=location_type == "Customs",
		)

	def _iter_fifo_batches(self, product, *, location_type, warehouse, for_release: bool = False):
		child_table = "`tabStock Entry Items`"
		parent_table = "`tabStock Entries`"

		if not frappe.db.table_exists("Stock Entries") or not frappe.db.table_exists("Stock Entry Items"):
			frappe.throw(
				_("Stock Entry tables are missing. Please run `bench migrate` to set up Stock Entries."),
				title=_("Stock Entries Not Available"),
			)
		if not self.import_shipment:
			frappe.throw(_("Import Shipment is required to reserve stock."), title=_("Shipment Required"))

		conditions = ["se.docstatus = 1", "sei.product = %s"]
		values: list = [product]

		if location_type == "Customs":
			conditions.append("se.status = 'At Customs'")
		else:
			conditions.append("se.status in ('Available', 'Reserved', 'Partially Issued')")
			if warehouse:
				conditions.append("se.warehouse = %s")
				values.append(warehouse)

		conditions.append("se.import_shipment = %s")
		values.append(self.import_shipment)

		if for_release:
			conditions.append("coalesce(sei.reserved_qty,0) > 0")
		else:
			conditions.append(
				"(coalesce(sei.received_qty,0) - coalesce(sei.reserved_qty,0) - coalesce(sei.issued_qty,0)) > 0"
			)

		query = f"""
			select
				sei.name as child_name,
				se.name as batch_name,
				se.status as status,
				se.warehouse as warehouse,
				coalesce(se.arrival_date, se.creation) as arrival_marker,
				se.creation as creation,
				coalesce(sei.reserved_qty,0) as reserved_qty,
				(coalesce(sei.received_qty,0) - coalesce(sei.reserved_qty,0) - coalesce(sei.issued_qty,0)) as available_qty
			from {child_table} sei
			inner join {parent_table} se on se.name = sei.parent
			where {" and ".join(conditions)}
			order by arrival_marker, se.creation
		"""
		return frappe.db.sql(query, tuple(values), as_dict=True)

	def _enforce_fifo(self, reservations):
		for batch_name, payload in reservations.items():
			if payload["from_customs"]:
				continue
			batch = frappe.get_doc("Stock Entries", batch_name)
			for entry in payload["rows"]:
				child = next((row for row in batch.items if row.name == entry["child_name"]), None)
				if not child:
					continue
				arrival_marker = batch.arrival_date or batch.creation
				if not frappe.db.table_exists("Stock Entry Items") or not frappe.db.table_exists("Stock Entries"):
					continue
				available_older = frappe.db.sql(
					"""
					select sei.name
					from `tabStock Entry Items` sei
					inner join `tabStock Entries` se on se.name = sei.parent
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
		net_receivable = self._net_receivable()
		total_paid = self._sum_payment_slips(verified_only=self.sales_type == "Cash")
		if exclude_invoice:
			# If excluding an invoice, avoid counting its total in net paid comparison
			net_receivable = max(net_receivable - flt(frappe.db.get_value("Plasticflow Invoice", exclude_invoice, "total_amount") or 0), 0)
		return max(net_receivable - total_paid, 0)

	def update_invoicing_progress(self):
		if self.is_new():
			return

		total_invoiced = self._get_total_invoiced_amount()
		net_receivable = self._net_receivable()
		total_paid = self._sum_payment_slips(verified_only=self.sales_type == "Cash")
		outstanding = max(net_receivable - total_paid, 0)
		latest_invoice = self._get_latest_invoice_name()
		invoice_target = flt(self.total_gross_amount or self.total_amount or 0)
		invoice_coverage = invoice_target <= PAYMENT_TOLERANCE or (
			total_invoiced >= invoice_target - PAYMENT_TOLERANCE
		)

		updates = {
			"invoiced_amount": total_invoiced,
			"outstanding_amount": outstanding,
			"invoice": latest_invoice,
		}

		if self.docstatus == 1:
			settled = self._maybe_mark_settled(
				total_paid=total_paid,
				expected_payment=net_receivable,
				outstanding=outstanding,
				total_invoiced=total_invoiced,
			)
			if outstanding <= PAYMENT_TOLERANCE:
				if invoice_coverage:
					updates["status"] = "Settled"
					self.status = "Settled"
					self._finalize_reservations()
				else:
					updates["status"] = "Payment Verified"
					self.status = "Payment Verified"
			else:
				target_status = "Payment Pending" if self.sales_type == "Cash" else "Credit Sales"
				if self.status != "Completed":
					updates["status"] = target_status
					self.status = target_status
				self._restore_reservations()
		else:
			settled = self._maybe_mark_settled(
				total_paid=total_paid,
				expected_payment=net_receivable,
				outstanding=outstanding,
				total_invoiced=total_invoiced,
			)

		if self.status == "Settled":
			updates["status"] = "Settled"

		gate_pass_dispatched = self._gate_pass_dispatched()
		if gate_pass_dispatched and self.sales_type == "Credit":
			# Credit orders complete only when dispatch is done and balance is cleared
			if outstanding <= PAYMENT_TOLERANCE:
				updates["status"] = "Completed"
				self.status = "Completed"
			else:
				updates["status"] = "Credit Sales"
				self.status = "Credit Sales"

		frappe.db.set_value("Sales Order", self.name, updates, update_modified=False)
		self.invoiced_amount = total_invoiced
		self.outstanding_amount = outstanding
		self.invoice = latest_invoice
		if "gate_pass" in updates:
			self.gate_pass = updates["gate_pass"]

	def create_invoice(self, invoice_amount=None):
		if self.docstatus != 1:
			frappe.throw(_("Submit the sales order before creating invoices."))

		is_cash = self.sales_type == "Cash"
		outstanding = self.get_outstanding_amount()
		total_gross = flt(self.total_gross_amount or self.total_amount or 0)
		total_invoiced = flt(self._get_total_invoiced_amount() or 0)
		remaining_gross = max(total_gross - total_invoiced, 0)

		if is_cash and not self._has_verified_payments():
			frappe.throw(_("Verify at least one payment slip before creating a cash invoice."))

		if remaining_gross <= PAYMENT_TOLERANCE:
			frappe.throw(_("This sales order is already fully invoiced."))

		amount = remaining_gross if invoice_amount is None else flt(invoice_amount)

		if amount <= PAYMENT_TOLERANCE:
			frappe.throw(_("Invoice amount must be greater than zero."))
		if amount - remaining_gross > PAYMENT_TOLERANCE:
			frappe.throw(
				_("Invoice amount cannot exceed the remaining gross sales ({0}).").format(
					frappe.utils.fmt_money(remaining_gross, currency=self.currency)
				)
			)

		invoice = self._build_invoice_doc(amount)
		invoice.insert(ignore_permissions=True)
		self._link_slips_to_invoice(invoice)
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

		total_gross = flt(self.total_gross_amount or self.total_amount)
		ratio = 1 if total_gross <= PAYMENT_TOLERANCE else min(1, flt(amount) / total_gross)

		last_item = None
		for item in self.items:
			base_qty = flt(item.quantity or 0)
			if base_qty <= 0:
				continue
			qty = base_qty * ratio
			if qty <= 0:
				continue
			base_rate = flt(item.rate or 0)
			inclusive_rate = base_rate * (1 + VAT_RATE)
			rate = inclusive_rate
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

	def _link_slips_to_invoice(self, invoice):
		if self.sales_type != "Cash":
			return
		for row in self.payment_slips:
			if (row.slip_status or "").lower() != "verified":
				continue
			if row.invoice:
				continue
			frappe.db.set_value(
				"Payment Slips",
				row.name,
				"invoice",
				invoice.name,
				update_modified=False,
			)
			row.invoice = invoice.name

	def create_gate_pass(self, allow_partial: bool = False):
		frappe.throw(_("Gate Pass is no longer used. Please create a Gate Pass Request via Loading Order."))


@frappe.whitelist()
def create_sales_invoice(sales_order, amount=None):
	so = frappe.get_doc("Sales Order", sales_order)
	so.check_permission("submit")
	invoice = so.create_invoice(invoice_amount=amount)
	return invoice.as_dict()


@frappe.whitelist()
def create_sales_order_gate_pass(sales_order):
	frappe.throw(_("Gate Pass is no longer used. Please create a Gate Pass Request via Loading Order."))
