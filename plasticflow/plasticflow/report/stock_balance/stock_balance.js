frappe.query_reports["Stock Balance"] = {
	filters: [
		{
			fieldname: "import_shipment",
			fieldtype: "Link",
			label: "Import Shipment",
			options: "Import Shipment",
		},
		{
			fieldname: "warehouse",
			fieldtype: "Link",
			label: "Warehouse",
			options: "Warehouse",
		},
		{
			fieldname: "display_uom",
			fieldtype: "Select",
			label: "Display UOM",
			options: "Kg\nTon",
			default: "Kg",
			on_change: (report) => report.refresh(),
		},
		{
			fieldname: "as_of_date",
			fieldtype: "Date",
			label: "As Of Date",
		},
	],
};
