import json

import frappe
from frappe.utils import cint


@frappe.whitelist()
def get_fifo_import_shipments(doctype, txt, searchfield, start, page_len=None, page_length=None, filters=None):
	filters = frappe.parse_json(filters) if filters else {}
	txt = txt or ""
	delivery_source = (filters or {}).get("delivery_source") or "Warehouse"
	location_type = "Customs" if delivery_source == "Direct from Customs" else "Warehouse"

	products = filters.get("products") or []
	if isinstance(products, str):
		try:
			products = json.loads(products)
		except (json.JSONDecodeError, TypeError):
			products = []
	products = [p for p in products if p]

	status_filter = (
		"se.status = 'At Customs'"
		if location_type == "Customs"
		else "se.status in ('Available', 'Reserved', 'Partially Issued')"
	)

	limit = cint(page_len or page_length) or 20
	offset = cint(start) or 0

	product_join = ""
	product_condition = ""
	sle_product_condition = ""

	if products:
		placeholders = ", ".join(["%s"] * len(products))
		product_join = f"""
			inner join `tabImport Shipment Item` isi
				on isi.parent = ish.name
				and isi.product in ({placeholders})
		"""
		sle_product_condition = f"and sle.product in ({placeholders})"

	values = []
	if products:
		values.extend(products)
	values.append(location_type)
	if products:
		values.extend(products)
	values.extend([f"%{txt}%", f"%{txt}%", limit, offset])

	query = f"""
		select
			ish.name,
			ish.import_reference
		from `tabImport Shipment` ish
		inner join `tabStock Ledger Entry` sle
			on sle.import_shipment = ish.name
		left join `tabStock Entries` se
			on se.import_shipment = ish.name
			and se.docstatus = 1
			and {status_filter}
		{product_join}
		where ish.docstatus = 1
			and sle.location_type = %s
			{sle_product_condition}
			and (ish.name like %s or ish.import_reference like %s)
		group by ish.name, ish.import_reference
		having sum(coalesce(sle.available_qty, 0)) > 0
		order by
			coalesce(
				min(coalesce(se.arrival_date, se.creation)),
				ish.arrival_date,
				ish.shipment_date,
				ish.creation
			),
			ish.creation
		limit %s offset %s
	"""

	return frappe.db.sql(query, tuple(values), as_list=True)
