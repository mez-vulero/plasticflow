import frappe
from frappe import _
from frappe.model.document import Document


class SalesOrderStatusUpdate(Document):
	pass


@frappe.whitelist()
def get_matching_orders(sales_type, current_status=None, customer=None,
						from_date=None, to_date=None, import_shipment=None):
	"""Return submitted Sales Orders matching the given filters."""
	conditions = ["so.docstatus = 1", "so.sales_type = %s"]
	values = [sales_type]

	if current_status:
		conditions.append("so.status = %s")
		values.append(current_status)
	if customer:
		conditions.append("so.customer = %s")
		values.append(customer)
	if from_date:
		conditions.append("so.order_date >= %s")
		values.append(from_date)
	if to_date:
		conditions.append("so.order_date <= %s")
		values.append(to_date)
	if import_shipment:
		conditions.append("so.import_shipment = %s")
		values.append(import_shipment)

	where_clause = " and ".join(conditions)

	return frappe.db.sql(
		f"""
		select
			so.name,
			so.customer,
			so.order_date,
			so.status,
			so.sales_type,
			so.total_gross_amount,
			so.outstanding_amount
		from `tabSales Order` so
		where {where_clause}
		order by so.order_date, so.creation
		""",
		tuple(values),
		as_dict=True,
	)


@frappe.whitelist()
def apply_status_change(sales_type, new_status, current_status=None, customer=None,
						from_date=None, to_date=None, import_shipment=None, reason=None):
	"""Bulk update status on matching Sales Orders."""
	if not new_status:
		frappe.throw(_("Please select a status to apply."))

	orders = get_matching_orders(
		sales_type=sales_type,
		current_status=current_status,
		customer=customer,
		from_date=from_date,
		to_date=to_date,
		import_shipment=import_shipment,
	)

	if not orders:
		frappe.throw(_("No matching Sales Orders found."))

	count = 0
	for order in orders:
		if order.status == new_status:
			continue
		frappe.db.set_value("Sales Order", order.name, "status", new_status, update_modified=False)
		if reason:
			frappe.get_doc("Sales Order", order.name).add_comment(
				"Info", f"Status changed to {new_status}. Reason: {reason}"
			)
		count += 1

	frappe.db.commit()

	frappe.msgprint(
		_("{0} Sales Order(s) updated to '{1}'.").format(count, new_status),
		indicator="green",
		alert=True,
	)

	return {"updated": count}
