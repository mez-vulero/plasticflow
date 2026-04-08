frappe.ui.form.on("Sales Order Status Update", {
	refresh(frm) {
		frm.disable_save();
		frm.trigger("load_preview");
	},

	sales_type_filter: load_preview,
	current_status_filter: load_preview,
	customer_filter: load_preview,
	from_date: load_preview,
	to_date: load_preview,
	import_shipment_filter: load_preview,

	apply_button(frm) {
		if (!frm.doc.new_status) {
			frappe.msgprint(__("Please select a status to apply."));
			return;
		}

		frappe.confirm(
			__("Are you sure you want to change the status of all matching orders to <b>{0}</b>?",
				[frm.doc.new_status]),
			() => {
				frappe.call({
					method: "plasticflow.plasticflow.doctype.sales_order_status_update.sales_order_status_update.apply_status_change",
					args: {
						sales_type: frm.doc.sales_type_filter,
						new_status: frm.doc.new_status,
						current_status: frm.doc.current_status_filter || "",
						customer: frm.doc.customer_filter || "",
						from_date: frm.doc.from_date || "",
						to_date: frm.doc.to_date || "",
						import_shipment: frm.doc.import_shipment_filter || "",
						reason: frm.doc.reason || "",
					},
					freeze: true,
					freeze_message: __("Updating statuses..."),
					callback(r) {
						if (r && r.message) {
							frm.trigger("load_preview");
						}
					},
				});
			}
		);
	},

	load_preview(frm) {
		if (!frm.doc.sales_type_filter) {
			frm.fields_dict.preview_html.$wrapper.html(
				'<p class="text-muted">Select a Sales Type to see matching orders.</p>'
			);
			return;
		}

		frappe.call({
			method: "plasticflow.plasticflow.doctype.sales_order_status_update.sales_order_status_update.get_matching_orders",
			args: {
				sales_type: frm.doc.sales_type_filter,
				current_status: frm.doc.current_status_filter || "",
				customer: frm.doc.customer_filter || "",
				from_date: frm.doc.from_date || "",
				to_date: frm.doc.to_date || "",
				import_shipment: frm.doc.import_shipment_filter || "",
			},
			callback(r) {
				const orders = (r && r.message) || [];
				if (!orders.length) {
					frm.fields_dict.preview_html.$wrapper.html(
						'<p class="text-muted">No matching orders found.</p>'
					);
					return;
				}

				let html = `<p class="text-muted">${orders.length} order(s) found</p>`;
				html += '<table class="table table-bordered table-sm">';
				html += '<thead><tr>';
				html += '<th>Sales Order</th><th>Customer</th><th>Date</th>';
				html += '<th>Status</th><th>Gross Amount</th><th>Outstanding</th>';
				html += '</tr></thead><tbody>';

				orders.forEach((o) => {
					const status_color = {
						"Payment Pending": "orange",
						"Payment Verified": "blue",
						"Invoiced": "green",
						"Credit Sales": "blue",
						"Completed": "green",
						"Held": "red",
					};
					const color = status_color[o.status] || "grey";

					html += '<tr>';
					html += `<td><a href="/app/sales-order/${o.name}">${o.name}</a></td>`;
					html += `<td>${o.customer || ""}</td>`;
					html += `<td>${o.order_date || ""}</td>`;
					html += `<td><span class="indicator-pill ${color}">${o.status}</span></td>`;
					html += `<td style="text-align:right">${format_currency(o.total_gross_amount || 0)}</td>`;
					html += `<td style="text-align:right">${format_currency(o.outstanding_amount || 0)}</td>`;
					html += '</tr>';
				});

				html += '</tbody></table>';
				frm.fields_dict.preview_html.$wrapper.html(html);
			},
		});
	},
});

function load_preview(frm) {
	frm.trigger("load_preview");
}
