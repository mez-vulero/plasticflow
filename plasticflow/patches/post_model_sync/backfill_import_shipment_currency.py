import frappe


def execute():
	frappe.reload_doc("plasticflow", "doctype", "import_shipment")

	default_currency = frappe.db.get_default("currency")
	if not default_currency:
		return

	# Ensure currency values exist for formatting currency fields (e.g., Declared Value)
	frappe.db.sql(
		"""
		UPDATE `tabImport Shipment`
		SET currency = %(currency)s
		WHERE IFNULL(currency, '') = ''
		""",
		{"currency": default_currency},
	)

	frappe.db.sql(
		"""
		UPDATE `tabImport Shipment`
		SET local_currency = %(currency)s
		WHERE IFNULL(local_currency, '') = ''
		""",
		{"currency": default_currency},
	)
