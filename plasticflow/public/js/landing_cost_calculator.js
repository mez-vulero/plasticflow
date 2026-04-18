const debounced_preview = frappe.utils.debounce((frm) => preview_calculator(frm), 400);

frappe.ui.form.on("Landing Cost Calculator", {
	refresh(frm) {
		set_row_currency_defaults(frm);
	},
	exchange_rate: debounced_preview,
	currency(frm) {
		set_row_currency_defaults(frm);
		debounced_preview(frm);
	},
	import_currency(frm) {
		set_row_currency_defaults(frm);
		debounced_preview(frm);
	},
	allocation_method: debounced_preview,
	default_selling_price_per_kg: debounced_preview,
	default_profit_tax_percent: debounced_preview,
});

frappe.ui.form.on("Landing Cost Calculator Item", {
	items_add(frm, cdt, cdn) {
		const row = frappe.get_doc(cdt, cdn);
		if (!row.selling_price_per_kg && frm.doc.default_selling_price_per_kg) {
			frappe.model.set_value(cdt, cdn, "selling_price_per_kg", frm.doc.default_selling_price_per_kg);
		}
		if (!row.profit_tax_percent && frm.doc.default_profit_tax_percent) {
			frappe.model.set_value(cdt, cdn, "profit_tax_percent", frm.doc.default_profit_tax_percent);
		}
		debounced_preview(frm);
	},
	quantity_tons: debounced_preview,
	price_per_ton_import: debounced_preview,
	base_amount_import: debounced_preview,
	selling_price_per_kg: debounced_preview,
	profit_tax_percent: debounced_preview,
	items_remove: debounced_preview,
	product(frm, cdt, cdn) {
		const row = frappe.get_doc(cdt, cdn);
		if (row.product && !row.item_name) {
			frappe.db.get_value("Product", row.product, "product_name").then((r) => {
				if (r.message && r.message.product_name) {
					frappe.model.set_value(cdt, cdn, "item_name", r.message.product_name);
				}
			});
		}
	},
});

frappe.ui.form.on("Landing Cost Calculator Cost", {
	costs_add(frm, cdt, cdn) {
		set_row_currency_defaults(frm, cdt, cdn);
		debounced_preview(frm);
	},
	cost_bucket(frm, cdt, cdn) {
		set_row_currency_defaults(frm, cdt, cdn);
		debounced_preview(frm);
	},
	cost_scope: debounced_preview,
	amount: debounced_preview,
	percentage_rate: debounced_preview,
	exchange_rate: debounced_preview,
	currency: debounced_preview,
	is_taxable: debounced_preview,
	apply_to_item: debounced_preview,
	costs_remove: debounced_preview,
});

frappe.ui.form.on("Landing Cost Calculator Tax", {
	taxes_add(frm, cdt, cdn) {
		const row = frappe.get_doc(cdt, cdn);
		if (!row.currency) {
			frappe.model.set_value(cdt, cdn, "currency", frm.doc.currency);
		}
		debounced_preview(frm);
	},
	cost_type: debounced_preview,
	cost_scope: debounced_preview,
	percentage: debounced_preview,
	exchange_rate: debounced_preview,
	currency: debounced_preview,
	apply_to_item: debounced_preview,
	taxes_remove: debounced_preview,
});

function set_row_currency_defaults(frm, cdt, cdn) {
	const rows = cdt && cdn ? [frappe.get_doc(cdt, cdn)] : frm.doc.costs || [];
	rows.forEach((row) => {
		if (row.doctype !== "Landing Cost Calculator Cost") return;
		const bucket = (row.cost_bucket || "").toLowerCase();
		const is_foreign = !bucket.includes("local");
		const target = is_foreign ? frm.doc.import_currency : frm.doc.currency;
		if (target && row.currency !== target) {
			frappe.model.set_value(row.doctype, row.name, "currency", target);
		}
		const target_rate =
			is_foreign && row.currency === frm.doc.import_currency
				? frm.doc.exchange_rate || 1
				: !is_foreign && row.currency === frm.doc.currency
					? 1
					: null;
		if (target_rate && Math.abs((Number(row.exchange_rate) || 0) - target_rate) > 0.000001) {
			frappe.model.set_value(row.doctype, row.name, "exchange_rate", target_rate);
		}
	});
}

function preview_calculator(frm) {
	if (!frm || frm.is_new() && (!frm.doc.items || !frm.doc.items.length)) {
		return;
	}
	if (!frm.doc.currency || !frm.doc.import_currency) {
		return;
	}

	frappe.call({
		method: "plasticflow.plasticflow.doctype.landing_cost_calculator.landing_cost_calculator.preview_totals",
		args: { doc: frm.doc },
		callback: ({ message }) => {
			if (!message) return;

			const parent_fields = [
				"total_quantity",
				"total_base_amount_local",
				"total_base_amount_import",
				"total_foreign_cost",
				"total_local_cost",
				"total_tax_cost",
				"total_landed_cost",
				"total_landed_cost_import",
				"avg_landed_cost_per_ton",
				"avg_landed_cost_per_kg",
				"avg_landed_cost_per_ton_import",
				"estimated_total_net_profit",
			];
			parent_fields.forEach((f) => {
				if (message[f] !== undefined) {
					frm.doc[f] = message[f];
					frm.refresh_field(f);
				}
			});

			(message.items || []).forEach((preview_row) => {
				const row = (frm.doc.items || []).find((r) => r.name === preview_row.name);
				if (!row) return;
				Object.keys(preview_row).forEach((key) => {
					if (key === "name") return;
					row[key] = preview_row[key];
				});
			});
			frm.refresh_field("items");
		},
	});
}
