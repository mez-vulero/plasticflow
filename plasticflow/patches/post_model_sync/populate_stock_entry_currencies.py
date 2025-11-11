import frappe


def execute():
	default_currency = frappe.db.get_default("currency")
	entries = frappe.get_all(
		"Stock Entries",
		fields=["name", "import_shipment", "import_currency", "local_currency"],
	)

	for entry in entries:
		import_currency = entry.import_currency
		local_currency = entry.local_currency

		if entry.import_shipment and frappe.db.exists("Import Shipment", entry.import_shipment):
			shipment = frappe.db.get_value(
				"Import Shipment",
				entry.import_shipment,
				["currency", "local_currency"],
				as_dict=True,
			)
			if shipment:
				import_currency = import_currency or shipment.currency
				local_currency = local_currency or shipment.local_currency or shipment.currency

		import_currency = import_currency or default_currency
		local_currency = local_currency or default_currency

		if not import_currency and not local_currency:
			continue

		if import_currency != entry.import_currency or local_currency != entry.local_currency:
			frappe.db.set_value(
				"Stock Entries",
				entry.name,
				{
					"import_currency": import_currency,
					"local_currency": local_currency,
				},
				update_modified=False,
			)
