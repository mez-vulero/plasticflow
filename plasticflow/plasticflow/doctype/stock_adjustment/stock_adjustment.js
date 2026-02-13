frappe.ui.form.on("Stock Adjustment", {
	import_shipment(frm) {
		if (!frm.doc.import_shipment) {
			frm.clear_table("items");
			frm.refresh_field("items");
			return;
		}

		const load_items = () => {
			frappe.call({
				method: "frappe.client.get",
				args: {
					doctype: "Import Shipment",
					name: frm.doc.import_shipment,
				},
				callback: (r) => {
					const shipment = r && r.message;
					if (!shipment || !shipment.items) {
						return;
					}
					frm.clear_table("items");
					(shipment.items || []).forEach((row) => {
						const item = frm.add_child("items");
						item.product = row.product;
						item.product_name = row.product_name;
						item.uom = row.uom;
						item.quantity = 0;
					});
					frm.refresh_field("items");
				},
			});
		};

		if (frm.doc.items && frm.doc.items.length) {
			frappe.confirm(
				"Replace existing adjustment items with the import shipment items?",
				() => load_items()
			);
		} else {
			load_items();
		}
	},
});
