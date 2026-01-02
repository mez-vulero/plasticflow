import frappe


RENAME_MAP = {
	"Plasticflow Push Subscription": "Push Subscription",
	"Plasticflow Invoice": "Invoice",
	"Plasticflow Invoice Item": "Invoice Item",
	"Plasticflow Stock Ledger Entry": "Stock Ledger Entry",
}

OPTION_TARGETS = [
	("DocField", "options"),
	("Custom Field", "options"),
	("DocType Link", "link_doctype"),
]

EQUAL_TARGETS = [
	("Report", "ref_doctype"),
	("Dashboard Chart", "report_ref_doctype"),
	("Dashboard Chart", "document_type"),
	("Number Card", "document_type"),
	("Notification", "document_type"),
	("Workflow", "document_type"),
	("Dynamic Link", "link_doctype"),
	("File", "attached_to_doctype"),
	("Comment", "reference_doctype"),
	("Communication", "reference_doctype"),
	("ToDo", "reference_type"),
	("Version", "ref_doctype"),
	("Property Setter", "doc_type"),
]

TEXT_TARGETS = [
	("Number Card", "filters_json"),
	("Workspace", "content"),
	("Workspace", "links"),
]


def _update_equal(doctype: str, column: str, old: str, new: str) -> None:
	if not frappe.db.has_column(doctype, column):
		return
	frappe.db.sql(
		f"""
		update `tab{doctype}`
		set `{column}` = %(new)s
		where `{column}` = %(old)s
		""",
		{"old": old, "new": new},
	)


def _replace_text(doctype: str, column: str, old: str, new: str) -> None:
	if not frappe.db.has_column(doctype, column):
		return
	frappe.db.sql(
		f"""
		update `tab{doctype}`
		set `{column}` = replace(`{column}`, %(old)s, %(new)s)
		where `{column}` like %(pattern)s
		""",
		{"old": old, "new": new, "pattern": f"%{old}%"},
	)


def execute():
	for old, new in RENAME_MAP.items():
		if frappe.db.exists("DocType", old) and not frappe.db.exists("DocType", new):
			frappe.rename_doc("DocType", old, new, force=True)

	for old, new in RENAME_MAP.items():
		for doctype, column in OPTION_TARGETS:
			_update_equal(doctype, column, old, new)

		for doctype, column in EQUAL_TARGETS:
			_update_equal(doctype, column, old, new)

		frappe.db.sql(
			"""
			update `tabProperty Setter`
			set value = %(new)s
			where property = 'options'
				and value = %(old)s
			""",
			{"old": old, "new": new},
		)

		for doctype, column in TEXT_TARGETS:
			_replace_text(doctype, column, old, new)
