const debounced_preview_totals = frappe.utils.debounce((frm) => preview_totals(frm), 400);

frappe.ui.form.on("Landing Cost Worksheet", {
	refresh(frm) {
		set_component_currency_defaults(frm);
	},
});

frappe.ui.form.on("Landing Cost Component", {
	cost_bucket(frm, cdt, cdn) {
		set_component_currency_defaults(frm, cdt, cdn);
		debounced_preview_totals(frm);
	},
	amount: debounced_preview_totals,
	exchange_rate: debounced_preview_totals,
	currency: debounced_preview_totals,
});

frappe.ui.form.on("Landing Cost Tax", {
	refresh: debounced_preview_totals,
	cost_scope: debounced_preview_totals,
	percentage: debounced_preview_totals,
	exchange_rate: debounced_preview_totals,
	currency: debounced_preview_totals,
	apply_to_item: debounced_preview_totals,
	cost_type: debounced_preview_totals,
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

function preview_totals(frm) {
	if (!frm || frm.is_new() || !frm.doc.import_shipment) {
		return;
	}

	frappe.call({
		method: "plasticflow.plasticflow.doctype.landing_cost_worksheet.landing_cost_worksheet.preview_totals",
		args: { doc: frm.doc },
		callback: ({ message }) => {
			if (!message) return;
			Object.assign(frm.doc, message);
			frm.refresh_field("total_additional_cost");
			frm.refresh_field("total_additional_cost_import");
			frm.refresh_field("tax_cost_total");
			frm.refresh_field("tax_cost_total_import");
			frm.refresh_field("total_landed_cost");
			frm.refresh_field("total_landed_cost_import");
			frm.refresh_field("avg_landed_cost");
			frm.refresh_field("avg_landed_cost_import");
			frm.refresh_field("foreign_cost_total");
			frm.refresh_field("local_cost_total");
			frm.refresh_field("total_quantity");
		},
	});
}
