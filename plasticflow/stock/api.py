import frappe
from frappe.utils import nowdate


def _make_item_row(customs_item):
    landed_rate = 0
    landed_amount = 0
    landed_rate_local = 0
    landed_amount_local = 0
    shipment_item_details = {}
    if customs_item.import_shipment_item:
        shipment_item_details = frappe.db.get_value(
            "Import Shipment Item",
            customs_item.import_shipment_item,
            [
                "landed_cost_rate",
                "landed_cost_amount",
                "landed_cost_rate_local",
                "landed_cost_amount_local",
                "purchase_order_item",
            ],
            as_dict=True,
        )
        if shipment_item_details:
            landed_rate = shipment_item_details.landed_cost_rate or 0
            landed_amount = shipment_item_details.landed_cost_amount or 0
            landed_rate_local = shipment_item_details.landed_cost_rate_local or 0
            landed_amount_local = shipment_item_details.landed_cost_amount_local or 0

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
		"import_shipment_item": customs_item.get("import_shipment_item"),
        "landed_cost_rate": landed_rate,
        "landed_cost_amount": landed_amount,
        "landed_cost_rate_local": landed_rate_local,
        "landed_cost_amount_local": landed_amount_local,
        "purchase_order_item": shipment_item_details.get("purchase_order_item") if shipment_item_details else None,
    }


@frappe.whitelist()
def get_stock_entry_template(customs_entry: str) -> dict:
	customs = frappe.get_doc("Customs Entry", customs_entry)
	items = [_make_item_row(item) for item in customs.items]
	return {
		"arrival_date": nowdate(),
		"warehouse": customs.destination_warehouse,
		"status": "Available" if customs.clearance_status == "At Warehouse" else "At Customs",
		"import_shipment": customs.import_shipment,
		"items": items,
	}
