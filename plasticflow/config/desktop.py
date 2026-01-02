from frappe import _


def get_data():
	return [
		{
			"module_name": "PlasticFlow",
			"category": "Modules",
			"label": _("PlasticFlow"),
			"color": "orange",
			"icon": "octicon octicon-briefcase",
			"image": "/assets/plasticflow/icons/plasticflow-icon.svg",
			"type": "module",
			"items": [
				{"type": "doctype", "name": "Purchase Order"},
				{"type": "doctype", "name": "Import Shipment"},
				{"type": "doctype", "name": "Landing Cost Worksheet"},
				{"type": "doctype", "name": "Supplier"},
				{"type": "doctype", "name": "Product"},
				{"type": "doctype", "name": "Warehouse"},
				{"type": "doctype", "name": "Stock Entries"},
				{"type": "doctype", "name": "Stock Ledger Entry"},
				{"type": "doctype", "name": "Customer"},
				{"type": "doctype", "name": "Banks"},
				{"type": "doctype", "name": "Broker"},
				{"type": "doctype", "name": "Sales Order"},
				{"type": "doctype", "name": "Invoice"},
				{"type": "doctype", "name": "Gate Pass Request"},
				{"type": "doctype", "name": "Delivery Note"},
				{"type": "doctype", "name": "Driver"},
				{"type": "doctype", "name": "Customs Documents"},
				{"type": "doctype", "name": "Unit of Measurement"},
				{"type": "report", "name": "PlasticFlow Dashboard", "is_query_report": False},
				{"type": "report", "name": "Plasticflow Stock By Location", "is_query_report": True},
				{"type": "report", "name": "PlasticFlow Profitability Summary", "is_query_report": False},
			],
		}
	]
