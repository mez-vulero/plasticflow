import frappe


def execute():
	"""Delete and re-import all PlasticFlow workspaces so dashboard changes take effect."""
	workspaces = frappe.get_all(
		"Workspace",
		filters={"module": "PlasticFlow"},
		pluck="name",
	)

	for ws in workspaces:
		frappe.delete_doc("Workspace", ws, force=True, ignore_permissions=True)

	frappe.db.commit()
