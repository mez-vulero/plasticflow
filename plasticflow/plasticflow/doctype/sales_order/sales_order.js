// Copyright (c) 2025, VuleroTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Sales Order", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) {
			return;
		}

		const outstanding = flt(frm.doc.outstanding_amount || 0);
		const can_create_invoice =
			outstanding > 0.001 &&
			((frm.doc.sales_type === "Cash" &&
				(frm.doc.status === "Payment Verified" || frm.doc.status === "Invoiced")) ||
				(frm.doc.sales_type === "Credit" &&
					(frm.doc.status === "Credit Sales" || frm.doc.status === "Invoiced")));

		if (can_create_invoice) {
			const label =
				frm.doc.sales_type === "Cash" ? __("Create Cash Invoice") : __("Create Credit Invoice");
			frm.add_custom_button(label, () => {
				frappe.prompt(
					{
						fieldname: "amount",
						label: __("Invoice Amount"),
						fieldtype: "Currency",
						options: frm.doc.currency || "currency",
						reqd: 1,
						default: outstanding,
					},
					(values) => {
						frappe.call({
							method: "plasticflow.plasticflow.doctype.sales_order.sales_order.create_sales_invoice",
							args: {
								sales_order: frm.doc.name,
								amount: values.amount,
							},
							callback: (r) => {
								if (!r.message) {
									return;
								}
								frappe.model.sync(r.message);
								frappe.set_route("Form", r.message.doctype, r.message.name);
							},
						});
					},
					__("Create Invoice")
				);
			});
		}

		if (frm.doc.status === "Invoiced" && !frm.doc.gate_pass) {
			frm.add_custom_button(__("Ready for Delivery"), () => {
				frappe.call({
					method: "plasticflow.plasticflow.doctype.sales_order.sales_order.create_sales_order_gate_pass",
					args: {
						sales_order: frm.doc.name,
					},
					callback: (r) => {
						if (!r.message) {
							return;
						}
						frappe.model.sync(r.message);
						frappe.set_route("Form", r.message.doctype, r.message.name);
					},
				});
			});
		}
	},
});
