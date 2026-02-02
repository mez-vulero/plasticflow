import frappe
from frappe.utils import cint


@frappe.whitelist()
def get_fifo_import_shipments(doctype, txt, searchfield, start, page_len=None, page_length=None, filters=None):
	filters = frappe.parse_json(filters) if filters else {}
	txt = txt or ""
	delivery_source = (filters or {}).get("delivery_source") or "Warehouse"
	location_type = "Customs" if delivery_source == "Direct from Customs" else "Warehouse"

	status_filter = (
		"se.status = 'At Customs'"
		if location_type == "Customs"
		else "se.status in ('Available', 'Reserved', 'Partially Issued')"
	)

	limit = cint(page_len or page_length) or 20
	offset = cint(start) or 0

	values = {
		"location_type": location_type,
		"txt": f"%{txt}%",
		"start": offset,
		"page_len": limit,
	}

	query = f"""
		select
			ish.name,
			ish.import_reference
		from `tabImport Shipment` ish
		inner join `tabStock Ledger Entry` sle on sle.import_shipment = ish.name
		left join `tabStock Entries` se on se.import_shipment = ish.name
			and se.docstatus = 1
			and {status_filter}
		where ish.docstatus = 1
			and sle.location_type = %(location_type)s
			and (ish.name like %(txt)s or ish.import_reference like %(txt)s)
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
		limit %(page_len)s offset %(start)s
	"""

	return frappe.db.sql(query, values, as_list=True)
