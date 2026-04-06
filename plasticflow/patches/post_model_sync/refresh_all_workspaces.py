import json
import os

import frappe


def execute():
	"""Delete and re-import all PlasticFlow workspaces so dashboard changes take effect."""

	# Clear any user default_workspace references to PlasticFlow workspaces
	# so users don't get locked out during the refresh
	pf_workspaces = frappe.get_all(
		"Workspace",
		filters={"module": "PlasticFlow"},
		pluck="name",
	)
	if pf_workspaces:
		placeholders = ", ".join(["%s"] * len(pf_workspaces))
		frappe.db.sql(
			f"""update `tabUser` set default_workspace = NULL
			where default_workspace in ({placeholders})""",
			tuple(pf_workspaces),
		)

	# Delete existing workspaces and their child roles
	for ws in pf_workspaces:
		frappe.db.delete("Has Role", {"parent": ws, "parenttype": "Workspace"})
		frappe.db.delete("Workspace", {"name": ws})

	frappe.db.commit()

	# Re-import from JSON files
	workspace_dir = os.path.join(
		frappe.get_app_path("plasticflow"),
		"plasticflow",
		"workspace",
	)

	if not os.path.isdir(workspace_dir):
		return

	for folder in sorted(os.listdir(workspace_dir)):
		json_path = os.path.join(workspace_dir, folder, f"{folder}.json")
		if not os.path.isfile(json_path):
			continue

		with open(json_path) as f:
			doc_data = json.load(f)

		doc_data["doctype"] = "Workspace"
		doc = frappe.get_doc(doc_data)
		doc.flags.ignore_permissions = True
		doc.flags.ignore_links = True
		doc.flags.ignore_mandatory = True
		doc.insert()

	frappe.db.commit()
