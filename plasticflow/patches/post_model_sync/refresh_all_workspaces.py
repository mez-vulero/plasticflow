import json
import os

import frappe


def execute():
	"""Delete and re-import all PlasticFlow workspaces so dashboard changes take effect."""
	# Delete existing workspaces
	workspaces = frappe.get_all(
		"Workspace",
		filters={"module": "PlasticFlow"},
		pluck="name",
	)

	for ws in workspaces:
		frappe.delete_doc("Workspace", ws, force=True, ignore_permissions=True)

	frappe.db.commit()

	# Re-import from JSON files
	# Workspace JSONs live under plasticflow/plasticflow/plasticflow/workspace/
	workspace_dir = os.path.join(
		frappe.get_app_path("plasticflow"),
		"plasticflow",
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
