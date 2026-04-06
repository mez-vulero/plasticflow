frappe.listview_settings["Sales Order"] = {
	filters: [
		["docstatus", "=", 1],
	],
	onload(listview) {
		listview.page.add_field({
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: [
				"",
				"Payment Pending",
				"Payment Verified",
				"Settled",
				"Credit Sales",
				"Completed",
				"Cancelled",
				"Held",
			],
			change() {
				listview.refresh();
			},
		});

		listview.page.add_field({
			fieldname: "sales_type",
			label: __("Sales Type"),
			fieldtype: "Select",
			options: ["", "Cash", "Credit"],
			change() {
				listview.refresh();
			},
		});

		listview.page.add_field({
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
			change() {
				listview.refresh();
			},
		});

		listview.page.add_field({
			fieldname: "import_shipment",
			label: __("Import Shipment"),
			fieldtype: "Link",
			options: "Import Shipment",
			change() {
				listview.refresh();
			},
		});
	},
};
