from frappe import _


def get_data():
	return [
		{
			"module_name": "PlasticFlow",
			"category": "Modules",
			"label": _("PlasticFlow"),
			"color": "blue",
			"icon": "octicon octicon-briefcase",
			"type": "module",
			"items": [
				{"type": "doctype", "name": "Customs Entry"},
				{"type": "doctype", "name": "Supplier"},
				{"type": "doctype", "name": "Product"},
				{"type": "doctype", "name": "Warehouse"},
				{"type": "doctype", "name": "Stock Batch"},
				{"type": "doctype", "name": "Customer"},
				{"type": "doctype", "name": "Sales Order"},
				{"type": "doctype", "name": "Plasticflow Invoice"},
				{"type": "doctype", "name": "Gate Pass"},
				{"type": "doctype", "name": "Delivery Note"},
				{"type": "doctype", "name": "Driver"},
				{"type": "report", "name": "PlasticFlow Dashboard", "is_query_report": False},
			],
		}
	]
