import frappe
from frappe.utils import nowdate


def _make_item_row(shipment_item):
	landed_amount = shipment_item.landed_cost_amount or 0
	landed_amount_local = shipment_item.landed_cost_amount_local or 0
	quantity = shipment_item.quantity or 0

	landed_rate = shipment_item.landed_cost_rate or (landed_amount / quantity if quantity else 0)
	landed_rate_local = shipment_item.landed_cost_rate_local or (
		landed_amount_local / quantity if quantity else 0
	)

	return {
		"product": shipment_item.product,
		"product_name": shipment_item.product_name
		or frappe.db.get_value("Product", shipment_item.product, "product_name"),
		"received_qty": quantity,
		"reserved_qty": 0,
		"issued_qty": 0,
		"uom": shipment_item.uom,
		"warehouse_location": shipment_item.get("warehouse_location"),
		"import_shipment_item": shipment_item.name,
		"purchase_order_item": shipment_item.purchase_order_item,
		"landed_cost_rate": landed_rate,
		"landed_cost_amount": landed_amount,
		"landed_cost_rate_local": landed_rate_local,
		"landed_cost_amount_local": landed_amount_local,
	}


@frappe.whitelist()
def get_stock_entry_template(import_shipment: str) -> dict:
	shipment = frappe.get_doc("Import Shipment", import_shipment)
	items = [_make_item_row(item) for item in shipment.items]
	return {
		"arrival_date": shipment.arrival_date or nowdate(),
		"warehouse": shipment.destination_warehouse,
		"status": "Available" if shipment.clearance_status == "At Warehouse" else "At Customs",
		"import_shipment": shipment.name,
		"items": items,
	}
