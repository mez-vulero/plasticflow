const VAT_RATE = 0.15;

frappe.ui.form.on("Sales Order", {
	refresh(frm) {
		recompute_parent_totals(frm);

		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Create Loading Order"), () => {
				frappe.call({
					method: "plasticflow.plasticflow.doctype.loading_order.loading_order.create_loading_order",
					args: { sales_order: frm.doc.name },
					freeze: true,
					freeze_message: __("Preparing Loading Order..."),
					callback: ({ message }) => {
						if (message && message.name) {
							frappe.set_route("Form", "Loading Order", message.name);
						}
					},
				});
			});

			frm.add_custom_button(__("Create Invoice"), () => {
				frappe.call({
					method: "plasticflow.plasticflow.doctype.sales_order.sales_order.create_sales_invoice",
					args: { sales_order: frm.doc.name },
					freeze: true,
					freeze_message: __("Preparing Invoice..."),
					callback: ({ message }) => {
						if (message && message.name) {
							frappe.set_route("Form", "Plasticflow Invoice", message.name);
						}
					},
				});
			});

		}
	},
});

frappe.ui.form.on("Sales Order Item", {
	rate: recompute_child,
	quantity: recompute_child,
	price_with_vat: recompute_child,
	withholding_rate: recompute_child,
});

function recompute_child(frm, cdt, cdn) {
	const row = frappe.get_doc(cdt, cdn);
	const qty = flt(row.quantity || 0);
	const rate = flt(row.rate || 0);
	const parent_withholding = flt(frm.doc.withholding_rate || 0);
	const parent_commission = flt(frm.doc.broker_commission_rate || 0);

	// VAT portion for the entire row (amount * VAT rate)
	row.amount = qty * rate;
	row.price_with_vat = row.amount * VAT_RATE;

	row.gross_amount = row.amount + flt(row.price_with_vat || 0);

	row.withholding_rate = parent_withholding;
	row.withholding_amount = row.amount * (parent_withholding / 100);
	row.net_amount = row.gross_amount - row.withholding_amount;

	row.commission_rate = parent_commission;
	row.commission_amount = row.gross_amount * (parent_commission / 100);

	frm.refresh_field("items");
	recompute_parent_totals(frm);
}

function recompute_parent_totals(frm) {
	const items = frm.doc.items || [];
	const totals = {
		total_quantity: 0,
		total_amount: 0,
		total_gross_amount: 0,
		total_withholding: 0,
		total_net_amount: 0,
	};

	items.forEach((row) => {
		totals.total_quantity += flt(row.quantity || 0);
		totals.total_amount += flt(row.amount || 0);
		totals.total_gross_amount += flt(row.gross_amount || 0);
		totals.total_withholding += flt(row.withholding_amount || 0);
		totals.total_net_amount += flt(row.net_amount || 0);
	});

	frm.set_value(totals);
	frm.refresh_fields(Object.keys(totals));
}
