frappe.ui.form.on("Purchase Order", {
	refresh(frm) {
		if (!frm.doc || ["Closed", "Cancelled"].includes(frm.doc.status)) {
			return;
		}

		frm.add_custom_button(__("Create Import Shipment"), () => {
			if (frm.doc.docstatus !== 1) {
				frappe.msgprint(__("Submit the purchase order before creating an import shipment."));
				return;
			}
			frm.call({
				method: "plasticflow.plasticflow.doctype.purchase_order.purchase_order.create_import_shipment",
				args: { purchase_order: frm.doc.name },
				freeze: true,
				freeze_message: __("Preparing import shipment..."),
				callback: ({ message }) => {
					if (!message) {
						return;
					}
					frappe.model.sync(message);
					frappe.set_route("Form", message.doctype || "Import Shipment", message.name);
				},
			});
		});
	},
});
