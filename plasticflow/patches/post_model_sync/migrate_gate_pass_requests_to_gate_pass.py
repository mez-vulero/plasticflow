import frappe
from frappe.utils import now_datetime


def _load_sales_order_items(sales_order):
	if not sales_order or not frappe.db.exists("Sales Order", sales_order):
		return []
	so = frappe.get_doc("Sales Order", sales_order)
	items = []
	for row in so.items:
		items.append(
			{
				"product": row.product,
				"product_name": row.product_name,
				"quantity": row.quantity,
				"uom": row.uom,
			}
		)
	return items


def _load_loading_order_items(loading_order):
	if not loading_order or not frappe.db.exists("Loading Order", loading_order):
		return [], None
	lo = frappe.get_doc("Loading Order", loading_order)
	items = []
	for row in lo.items:
		items.append(
			{
				"product": row.product,
				"product_name": row.product_name,
				"quantity": row.quantity,
				"uom": row.uom,
			}
		)
	return items, lo


def execute():
	if not frappe.db.exists("DocType", "Gate Pass"):
		return
	if not frappe.db.exists("DocType", "Gate Pass Request"):
		return

	gpr_rows = frappe.db.get_all(
		"Gate Pass Request",
		fields=[
			"name",
			"sales_order",
			"loading_order",
			"driver_name",
			"plate_number",
			"dispatched_on",
			"modified",
		],
	)
	if not gpr_rows:
		return

	mapping = {}

	for gpr in gpr_rows:
		name = gpr.name
		existing = None
		if gpr.loading_order:
			existing = frappe.db.get_value("Gate Pass", {"loading_order": gpr.loading_order}, "name")
		if not existing and gpr.sales_order:
			existing = frappe.db.get_value(
				"Gate Pass",
				{"sales_order": gpr.sales_order},
				"name",
				order_by="creation desc",
			)
		if existing:
			mapping[name] = existing
			continue

		items, lo = _load_loading_order_items(gpr.loading_order)
		if not items:
			items = _load_sales_order_items(gpr.sales_order)

		customer = None
		destination = None
		driver_name = gpr.driver_name
		plate_number = gpr.plate_number

		if lo:
			customer = lo.customer
			destination = lo.destination or customer
			driver_name = driver_name or lo.driver_name
			plate_number = plate_number or lo.vehicle_plate
		elif gpr.sales_order and frappe.db.exists("Sales Order", gpr.sales_order):
			so = frappe.get_doc("Sales Order", gpr.sales_order)
			customer = so.customer
			destination = customer
			driver_name = driver_name or so.driver_name
			plate_number = plate_number or so.plate_number

		gp = frappe.new_doc("Gate Pass")
		gp.sales_order = gpr.sales_order
		gp.loading_order = gpr.loading_order
		gp.customer = customer
		gp.destination = destination or customer
		gp.driver_name = driver_name
		gp.plate_number = plate_number
		gp.generated_on = gpr.dispatched_on or gpr.modified or now_datetime()
		for row in items:
			gp.append("items", row)
		gp.insert(ignore_permissions=True)
		mapping[name] = gp.name

	for gpr_name, gp_name in mapping.items():
		frappe.db.set_value(
			"Sales Order",
			{"gate_pass": gpr_name},
			"gate_pass",
			gp_name,
			update_modified=False,
		)
		frappe.db.set_value(
			"Loading Order",
			{"gate_pass_request": gpr_name},
			"gate_pass_request",
			gp_name,
			update_modified=False,
		)
		frappe.db.set_value(
			"Invoice",
			{"gate_pass": gpr_name},
			"gate_pass",
			gp_name,
			update_modified=False,
		)
		frappe.db.set_value(
			"Delivery Note",
			{"gate_pass": gpr_name},
			"gate_pass",
			gp_name,
			update_modified=False,
		)

	for gpr in gpr_rows:
		frappe.db.delete("Gate Pass Request", {"name": gpr.name})

	# Clear orphan links that still point to missing gate passes
	for doctype, field in [
		("Sales Order", "gate_pass"),
		("Loading Order", "gate_pass_request"),
		("Invoice", "gate_pass"),
		("Delivery Note", "gate_pass"),
	]:
		if not frappe.db.table_exists(doctype):
			continue
		frappe.db.sql(
			f"""
			update `tab{doctype}`
			set `{field}` = NULL
			where `{field}` is not null
				and `{field}` not in (select name from `tabGate Pass`)
			"""
		)
