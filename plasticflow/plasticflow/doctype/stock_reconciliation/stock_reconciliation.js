frappe.ui.form.on("Stock Reconciliation", {
	location_type(frm) {
		refresh_all_current_quantities(frm);
	},
	warehouse(frm) {
		refresh_all_current_quantities(frm);
	},
});

frappe.ui.form.on("Stock Reconciliation Item", {
	product(frm, cdt, cdn) {
		const item = frappe.get_doc(cdt, cdn);
		if (!item.product) return;

		frappe.db.get_value("Product", item.product, ["product_name", "uom"]).then((r) => {
			if (r && r.message) {
				frappe.model.set_value(cdt, cdn, "product_name", r.message.product_name);
				frappe.model.set_value(cdt, cdn, "uom", r.message.uom);
			}
		});

		fetch_current_qty(frm, cdt, cdn);
	},
	target_qty(frm, cdt, cdn) {
		const item = frappe.get_doc(cdt, cdn);
		frappe.model.set_value(cdt, cdn, "difference",
			flt(item.target_qty) - flt(item.current_qty));
	},
});

function fetch_current_qty(frm, cdt, cdn) {
	const item = frappe.get_doc(cdt, cdn);
	if (!item.product) return;

	frappe.call({
		method: "plasticflow.plasticflow.doctype.stock_reconciliation.stock_reconciliation.get_current_stock",
		args: {
			product: item.product,
			location_type: frm.doc.location_type || "Warehouse",
			warehouse: frm.doc.warehouse || "",
		},
		callback(r) {
			if (r && r.message !== undefined) {
				frappe.model.set_value(cdt, cdn, "current_qty", r.message);
				frappe.model.set_value(cdt, cdn, "difference",
					flt(item.target_qty) - flt(r.message));
			}
		},
	});
}

function refresh_all_current_quantities(frm) {
	(frm.doc.items || []).forEach((item) => {
		if (item.product) {
			fetch_current_qty(frm, item.doctype, item.name);
		}
	});
}
