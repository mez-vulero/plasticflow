// Copyright (c) 2026, VuleroTech and contributors
// For license information, please see license.txt

const VAT_RATE = 0.15;

frappe.ui.form.on("Proforma Invoice", {
	refresh(frm) {
		recompute_parent_totals(frm);

		if (frm.doc.docstatus !== 1 || frm.doc.status === "Converted") {
			return;
		}

		frm.add_custom_button(__("Create Sales Order"), () => {
			frappe.call({
				method: "plasticflow.plasticflow.doctype.proforma_invoice.proforma_invoice.create_sales_order",
				args: { proforma_invoice: frm.doc.name },
				freeze: true,
				freeze_message: __("Preparing Sales Order..."),
				callback: ({ message }) => {
					if (message && message.name) {
						frappe.set_route("Form", "Sales Order", message.name);
					}
				},
			});
		});
	},
});

frappe.ui.form.on("Proforma Invoice Item", {
	rate: recompute_child,
	quantity: recompute_child,
});

function recompute_child(frm, cdt, cdn) {
	const row = frappe.get_doc(cdt, cdn);
	const qty = flt(row.quantity || 0);
	const rate = flt(row.rate || 0);

	const base_amount = qty * rate;
	const vat_total = base_amount * VAT_RATE;
	const gross_amount = base_amount + vat_total;

	row.amount = base_amount;
	row.price_with_vat = vat_total;
	row.gross_amount = gross_amount;

	frm.refresh_field("items");
	recompute_parent_totals(frm);
}

function recompute_all_rows(frm) {
	const rows = frm.doc.items || [];
	rows.forEach((row) => {
		recompute_child(frm, row.doctype, row.name);
	});
}

function recompute_parent_totals(frm) {
	const items = frm.doc.items || [];
	const totals = {
		total_quantity: 0,
		total_amount: 0,
		total_vat: 0,
		total_gross_amount: 0,
	};

	items.forEach((row) => {
		totals.total_quantity += flt(row.quantity || 0);
		totals.total_amount += flt(row.amount || 0);
		totals.total_vat += flt(row.price_with_vat || 0);
		totals.total_gross_amount += flt(row.gross_amount || 0);
	});

	frm.set_value(totals);
	frm.refresh_fields(Object.keys(totals));
}
