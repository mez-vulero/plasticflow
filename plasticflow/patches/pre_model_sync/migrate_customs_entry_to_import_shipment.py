import frappe


def execute():
	if not frappe.db.table_exists("Customs Entry"):
		return

	customs_entries = frappe.db.get_all(
		"Customs Entry",
		fields=[
			"name",
			"import_shipment",
			"arrival_date",
			"customs_station",
			"bill_of_lading",
			"container_no",
			"clearance_status",
			"cleared_on",
			"destination_warehouse",
			"total_declared_value",
			"stock_entry",
			"remarks",
		],
	)

	for entry in customs_entries:
		import_shipment = entry.import_shipment
		if not import_shipment or not frappe.db.exists("Import Shipment", import_shipment):
			continue

		update_map = {
			"arrival_date": entry.arrival_date,
			"customs_station": entry.customs_station,
			"bill_of_lading": entry.bill_of_lading,
			"container_no": entry.container_no,
			"clearance_status": entry.clearance_status or "Received",
			"cleared_on": entry.cleared_on,
			"destination_warehouse": entry.destination_warehouse,
			"total_declared_value": entry.total_declared_value,
			"stock_entry": entry.stock_entry,
			"remarks": entry.remarks,
		}
		frappe.db.set_value("Import Shipment", import_shipment, update_map, update_modified=False)

		if entry.stock_entry and frappe.db.exists("Stock Entries", entry.stock_entry):
			frappe.db.set_value(
				"Stock Entries",
				entry.stock_entry,
				{"import_shipment": import_shipment},
				update_modified=False,
			)

	child_rows = frappe.db.get_all(
		"Customs Entry Item",
		fields=["import_shipment_item", "warehouse_location"],
	)
	for row in child_rows:
		if not row.import_shipment_item or not row.warehouse_location:
			continue
		if frappe.db.exists("Import Shipment Item", row.import_shipment_item):
			frappe.db.set_value(
				"Import Shipment Item",
				row.import_shipment_item,
				{"warehouse_location": row.warehouse_location},
				update_modified=False,
			)

	frappe.reload_doc("plasticflow", "doctype", "stock_entries")
	frappe.reload_doc("plasticflow", "doctype", "stock_entry_items")

	if frappe.db.table_exists("Customs Documents"):
		customs_docs = frappe.db.get_all(
			"Customs Documents",
			filters={"parenttype": "Customs Entry"},
			fields=["name", "parent", "parentfield"],
		)
		for doc in customs_docs:
			import_shipment = frappe.db.get_value("Customs Entry", doc.parent, "import_shipment")
			if not import_shipment or not frappe.db.exists("Import Shipment", import_shipment):
				continue
			frappe.db.set_value(
				"Customs Documents",
				doc.name,
				{
					"parent": import_shipment,
					"parenttype": "Import Shipment",
					"parentfield": "customs_documents",
				},
				update_modified=False,
			)

	if frappe.db.table_exists("tabStock Entries"):
		try:
			frappe.db.sql_ddl("alter table `tabStock Entries` drop column `customs_entry`")
		except Exception:
			pass
	if frappe.db.table_exists("tabStock Entry Items"):
		try:
			frappe.db.sql_ddl("alter table `tabStock Entry Items` drop column `customs_entry_item`")
		except Exception:
			pass
	if frappe.db.table_exists("tabPlasticflow Stock Ledger Entry"):
		try:
			frappe.db.sql_ddl("alter table `tabPlasticflow Stock Ledger Entry` drop column `customs_entry`")
		except Exception:
			pass

	if frappe.db.exists("DocType", "Customs Entry"):
		frappe.delete_doc("DocType", "Customs Entry", ignore_permissions=True, force=1)
	if frappe.db.exists("DocType", "Customs Entry Item"):
		frappe.delete_doc("DocType", "Customs Entry Item", ignore_permissions=True, force=1)

	if frappe.db.table_exists("Customs Entry"):
		frappe.db.sql_ddl("drop table if exists `tabCustoms Entry`")
	if frappe.db.table_exists("Customs Entry Item"):
		frappe.db.sql_ddl("drop table if exists `tabCustoms Entry Item`")
