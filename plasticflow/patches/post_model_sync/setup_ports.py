import frappe


def execute():
	frappe.reload_doc("plasticflow", "doctype", "ports")
	frappe.reload_doc("plasticflow", "doctype", "import_shipment")

	if not frappe.db.table_exists("Import Shipment"):
		return

	existing_ports = set(frappe.get_all("Ports", pluck="name")) if frappe.db.table_exists("Ports") else set()
	shipments = frappe.get_all(
		"Import Shipment",
		fields=["name", "port_of_loading", "port_of_discharge"],
	)

	pending_ports = set()
	for shipment in shipments:
		for field in ("port_of_loading", "port_of_discharge"):
			value = shipment.get(field)
			if not value:
				continue
			if value not in existing_ports:
				pending_ports.add(value)

	for port_name in sorted(pending_ports):
		if frappe.db.exists("Ports", port_name):
			continue

		doc = frappe.new_doc("Ports")
		doc.port_name = port_name
		doc.insert(ignore_permissions=True)
