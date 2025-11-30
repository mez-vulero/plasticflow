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
	clearance_status(frm) {
		// Stamp cleared date when marked cleared
		if (frm.doc.clearance_status === "Cleared" && !frm.doc.cleared_on) {
			frm.set_value("cleared_on", frappe.datetime.get_today());
		}
	},
});

function create_landing_cost_worksheet(frm) {
	const proceed = () => {
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
	};

	if (!frm.doc.name || frm.doc.__islocal || frm.is_dirty()) {
		frm.save().then(() => proceed());
		return;
	}

	proceed();
}
