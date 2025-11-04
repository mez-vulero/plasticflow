frappe.ui.form.on("Import Shipment", {
	refresh(frm) {
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(
				__("New Landing Cost Worksheet"),
				() => {
					frappe.route_options = {
						import_shipment: frm.doc.name,
						purchase_order: frm.doc.purchase_order,
					};
					frappe.new_doc("Landing Cost Worksheet");
				},
				__("Create")
			);
		}

		if (frm.doc.purchase_order) {
			frm.add_custom_button(
				__("View Purchase Order"),
				() => frappe.set_route("Form", "Purchase Order", frm.doc.purchase_order),
				__("View")
			);
		}
	},
});
