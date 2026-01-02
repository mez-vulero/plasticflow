frappe.provide("plasticflow.number_card");

plasticflow.number_card.extend_currency_options = function (frm) {
	if (frm.doc.type !== "Document Type" || !frm.doc.document_type) {
		return;
	}

	if (frm.doc.document_type !== "Invoice") {
		return;
	}

	frappe.model.with_doctype(frm.doc.document_type, () => {
		const meta = frappe.get_meta(frm.doc.document_type);
		const currency_fields =
			meta?.fields?.filter(
				(df) => df.fieldtype === "Currency" && (!df.options || df.options === "currency")
			) || [];

		if (!currency_fields.length) {
			return;
		}

		const field = frm.fields_dict.aggregate_function_based_on;
		const existing_options = Array.isArray(field.df.options)
			? field.df.options.slice()
			: [];
		const existing_values = new Set(
			existing_options.map((opt) => (typeof opt === "string" ? opt : opt.value))
		);

		let updated = false;
		currency_fields.forEach((df) => {
			if (!existing_values.has(df.fieldname)) {
				existing_options.push({ label: df.label, value: df.fieldname });
				existing_values.add(df.fieldname);
				updated = true;
			}
		});

		if (updated) {
			frm.set_df_property(
				"aggregate_function_based_on",
				"options",
				existing_options
			);
		}

		if (
			!frm.doc.aggregate_function_based_on &&
			existing_values.has("total_amount") &&
			frm.doc.name === "Total Revenue"
		) {
			frm.set_value("aggregate_function_based_on", "total_amount");
		}

		if (
			!frm.doc.aggregate_function_based_on &&
			existing_values.has("outstanding_amount") &&
			frm.doc.name === "Outstanding Amount"
		) {
			frm.set_value("aggregate_function_based_on", "outstanding_amount");
		}
	});
};

frappe.ui.form.on("Number Card", {
	refresh(frm) {
		plasticflow.number_card.extend_currency_options(frm);
	},

	document_type(frm) {
		plasticflow.number_card.extend_currency_options(frm);
	},
});
