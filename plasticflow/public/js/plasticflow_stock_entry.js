frappe.ui.form.on('Plasticflow Stock Entry', {
	customs_entry(frm) {
		if (!frm.doc.customs_entry) {
			return;
		}

		frm.call({
			method: 'plasticflow.stock.api.get_stock_entry_template',
			args: { customs_entry: frm.doc.customs_entry },
			freeze: true,
			callback: ({ message }) => {
				if (!message) {
					return;
				}

				if (!frm.doc.arrival_date) {
					frm.set_value('arrival_date', message.arrival_date);
				}

				if (message.warehouse && !frm.doc.warehouse) {
					frm.set_value('warehouse', message.warehouse);
				}

				frm.set_value('status', message.status);

				frm.clear_table('items');
				(message.items || []).forEach((row) => {
					frm.add_child('items', row);
				});
				frm.refresh_field('items');
			},
		});
	},
});
