frappe.ui.form.on('Stock Entries', {
	import_shipment(frm) {
		if (!frm.doc.import_shipment) {
			return;
		}

		frm.call({
			method: 'plasticflow.stock.api.get_stock_entry_template',
			args: { import_shipment: frm.doc.import_shipment },
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

				if (message.import_shipment && !frm.doc.import_shipment) {
					frm.set_value('import_shipment', message.import_shipment);
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
