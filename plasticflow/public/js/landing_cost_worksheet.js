frappe.ui.form.on("Landing Cost Worksheet", {
	refresh(frm) {
		set_component_currency_defaults(frm);
	},
});

frappe.ui.form.on("Landing Cost Component", {
	cost_bucket(frm, cdt, cdn) {
		set_component_currency_defaults(frm, cdt, cdn);
	},
});

function set_component_currency_defaults(frm, cdt, cdn) {
	const rows = cdt && cdn ? [frappe.get_doc(cdt, cdn)] : frm.doc.cost_components || [];
	rows.forEach((row) => {
		const bucket = (row.cost_bucket || "").toLowerCase();
		let target = null;
		if (bucket.includes("foreign")) {
			target = "USD";
		} else if (bucket.includes("local")) {
			target = "ETB";
		}

		if (target && row.currency !== target) {
			frappe.model.set_value(row.doctype, row.name, "currency", target);
		}
	});
}
