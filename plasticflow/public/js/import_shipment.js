frappe.ui.form.on("Import Shipment", {
	refresh(frm) {
		if (frm.doc.docstatus < 2) {
			frm.add_custom_button(__("Landing Cost Worksheet"), () => create_landing_cost_worksheet(frm));
		}

		if (frm.doc.purchase_order) {
			frm.add_custom_button(__("View Purchase Order"), () =>
				frappe.set_route("Form", "Purchase Order", frm.doc.purchase_order)
			);
		}
	},
});

function create_landing_cost_worksheet(frm) {
	if (!frm.doc.name) {
		return;
	}

	if (frm.doc.docstatus !== 1) {
		frappe.msgprint(__("Submit the import shipment before creating a landing cost worksheet."));
		return;
	}

	frappe.call({
		method: "plasticflow.plasticflow.doctype.import_shipment.import_shipment.create_landing_cost_worksheet",
		args: { import_shipment: frm.doc.name },
		freeze: true,
		freeze_message: __("Preparing Landing Cost Worksheet..."),
		callback: ({ message }) => {
			if (!message || !message.name) {
				return;
			}

			if (message.status === "existing") {
				frappe.show_alert({
					message: __("Opening existing worksheet {0}", [message.name]),
					indicator: "blue",
				});
			}

			frappe.set_route("Form", "Landing Cost Worksheet", message.name);
		},
	});
}
