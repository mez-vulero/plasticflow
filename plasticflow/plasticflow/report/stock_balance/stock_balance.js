frappe.query_reports["Stock Balance"] = {
	onload(report) {
		const display_filter = report.get_filter("display_uom");
		if (display_filter && !display_filter.get_value()) {
			display_filter.set_value("Kg");
		}
		if (display_filter) {
			display_filter.df.on_change = () => report.refresh();
			display_filter.refresh();
		}
	},
};
