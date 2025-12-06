frappe.ui.form.on("Purchase Order", {
	refresh(frm) {
		if (!frm.doc || ["Closed", "Cancelled"].includes(frm.doc.status)) {
			return;
		}

		const render_import_actions = (remaining_qty) => {
			const has_remaining = (remaining_qty || 0) > 0.0001;
			const tx_area = frm.dashboard?.transactions_area;
			const new_btns = tx_area?.find('.btn-new-doc[data-doctype="Import Shipment"]') || [];

			// Hide default new buttons; rely on validated custom button instead
			if (new_btns.length) {
				new_btns.hide();
			}

			frm.remove_custom_button(__("Create Import Shipment"));

			if (!has_remaining) {
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
		};

		if (frm.doc.docstatus === 1) {
			frappe.call({
				method: "plasticflow.plasticflow.doctype.purchase_order.purchase_order.get_remaining_shipment_quantity",
				args: { purchase_order: frm.doc.name },
				callback: ({ message }) => {
					const remaining = message ? message.remaining_quantity : 0;
					render_import_actions(remaining);
				},
			});
		} else {
			render_import_actions(1);
		}
	},
});

frappe.ui.form.on("Purchase Order Item", {
	product(frm, cdt, cdn) {
		const row = frappe.get_doc(cdt, cdn);
		if (!row.product) return;

		frappe.db
			.get_value("Product", row.product, "uom")
			.then(({ message }) => {
				if (message && message.uom) {
					frappe.model.set_value(cdt, cdn, "uom", message.uom);
				}
			})
			.catch(() => {});
	},
});
