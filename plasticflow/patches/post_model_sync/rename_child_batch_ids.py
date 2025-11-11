import frappe


def execute():
	rename_import_shipment_items()
	rename_stock_entry_items()


def rename_import_shipment_items():
	shipments = frappe.get_all("Import Shipment", pluck="name")
	for shipment in shipments:
		items = frappe.get_all(
			"Import Shipment Item",
			filters={"parent": shipment},
			fields=["name"],
			order_by="idx asc",
		)
		sequence = 1
		for item in items:
			target = f"{shipment}-ITEM-{sequence:03d}"
			if item.name == target:
				sequence += 1
				continue

			while target != item.name and frappe.db.exists("Import Shipment Item", target):
				sequence += 1
				target = f"{shipment}-ITEM-{sequence:03d}"

			if item.name != target:
				frappe.rename_doc(
					"Import Shipment Item",
					item.name,
					target,
					force=True,
					show_alert=False,
				)

			sequence += 1


def rename_stock_entry_items():
	entries = frappe.get_all("Stock Entries", pluck="name")
	for entry in entries:
		items = frappe.get_all(
			"Stock Entry Items",
			filters={"parent": entry},
			fields=["name"],
			order_by="idx asc",
		)
		sequence = 1
		for item in items:
			target = f"{entry}-BATCH-{sequence:03d}"
			if item.name == target:
				sequence += 1
				continue

			while target != item.name and frappe.db.exists("Stock Entry Items", target):
				sequence += 1
				target = f"{entry}-BATCH-{sequence:03d}"

			if item.name != target:
				frappe.rename_doc(
					"Stock Entry Items",
					item.name,
					target,
					force=True,
					show_alert=False,
				)

			sequence += 1
