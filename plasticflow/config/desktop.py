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
				{"type": "doctype", "name": "Customs Entry"},
				{"type": "doctype", "name": "Supplier"},
				{"type": "doctype", "name": "Product"},
				{"type": "doctype", "name": "Warehouse"},
				{"type": "doctype", "name": "Plasticflow Stock Entry"},
				{"type": "doctype", "name": "Plasticflow Stock Ledger Entry"},
				{"type": "doctype", "name": "Customer"},
				{"type": "doctype", "name": "Sales Order"},
				{"type": "doctype", "name": "Plasticflow Invoice"},
				{"type": "doctype", "name": "Gate Pass"},
				{"type": "doctype", "name": "Delivery Note"},
				{"type": "doctype", "name": "Driver"},
				{"type": "doctype", "name": "Customs Documents"},
				{"type": "doctype", "name": "Unit of Measurement"},
				{"type": "report", "name": "PlasticFlow Dashboard", "is_query_report": False},
				{"type": "report", "name": "Plasticflow Stock By Location", "is_query_report": True},
			],
		}
	]
