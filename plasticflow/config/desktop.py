from frappe import _


def get_data():
	return [
		{
			"module_name": "Customs",
			"category": "Modules",
			"label": _("Customs"),
			"color": "blue",
			"icon": "octicon octicon-briefcase",
			"type": "module",
			"items": [
				{"type": "doctype", "name": "Customs Entry"},
				{"type": "doctype", "name": "Supplier"},
			],
		},
		{
			"module_name": "Stock",
			"category": "Modules",
			"label": _("Stock"),
			"color": "green",
			"icon": "octicon octicon-package",
			"type": "module",
			"items": [
				{"type": "doctype", "name": "Product"},
				{"type": "doctype", "name": "Warehouse"},
				{"type": "doctype", "name": "Stock Batch"},
			],
		},
		{
			"module_name": "Sales",
			"category": "Modules",
			"label": _("Sales"),
			"color": "orange",
			"icon": "octicon octicon-graph",
			"type": "module",
			"items": [
				{"type": "doctype", "name": "Customer"},
				{"type": "doctype", "name": "Sales Order"},
			],
		},
		{
			"module_name": "Finance",
			"category": "Modules",
			"label": _("Finance"),
			"color": "purple",
			"icon": "octicon octicon-credit-card",
			"type": "module",
			"items": [{"type": "doctype", "name": "Plasticflow Invoice"}],
		},
		{
			"module_name": "Logistics",
			"category": "Modules",
			"label": _("Logistics"),
			"color": "red",
			"icon": "octicon octicon-truck",
			"type": "module",
			"items": [
				{"type": "doctype", "name": "Gate Pass"},
				{"type": "doctype", "name": "Delivery Note"},
				{"type": "doctype", "name": "Driver"},
			],
		},
		{
			"module_name": "Reports",
			"category": "Modules",
			"label": _("Reports"),
			"color": "teal",
			"icon": "octicon octicon-dashboard",
			"type": "module",
			"items": [
				{"type": "report", "name": "PlasticFlow Dashboard", "is_query_report": False},
			],
		},
	]
