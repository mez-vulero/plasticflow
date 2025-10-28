import frappe
from frappe.utils import nowdate


def _make_item_row(customs_item):
	return {
		"product": customs_item.product,
		"product_name": customs_item.product_name
			or frappe.db.get_value("Product", customs_item.product, "product_name"),
		"received_qty": customs_item.quantity,
		"reserved_qty": 0,
		"issued_qty": 0,
		"uom": customs_item.uom,
		"warehouse_location": customs_item.get("warehouse_location"),
		"customs_entry_item": customs_item.name,
	}


@frappe.whitelist()
def get_stock_entry_template(customs_entry: str) -> dict:
	customs = frappe.get_doc("Customs Entry", customs_entry)
	items = [_make_item_row(item) for item in customs.items]
	return {
		"arrival_date": nowdate(),
		"warehouse": customs.destination_warehouse,
		"status": "Available" if customs.clearance_status == "At Warehouse" else "At Customs",
		"items": items,
	}
