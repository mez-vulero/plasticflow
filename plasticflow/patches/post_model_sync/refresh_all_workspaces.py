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
	workspace_dir = os.path.join(
		os.path.dirname(os.path.abspath(__file__)),
		"..",
		"..",
		"plasticflow",
		"workspace",
	)
	workspace_dir = os.path.normpath(workspace_dir)

	if not os.path.isdir(workspace_dir):
		return

	for folder in os.listdir(workspace_dir):
		json_path = os.path.join(workspace_dir, folder, f"{folder}.json")
		if not os.path.isfile(json_path):
			continue

		with open(json_path) as f:
			doc_data = json.load(f)

		doc_data["doctype"] = "Workspace"
		if frappe.db.exists("Workspace", doc_data.get("name")):
			existing = frappe.get_doc("Workspace", doc_data["name"])
			existing.update(doc_data)
			existing.flags.ignore_permissions = True
			existing.save()
		else:
			doc = frappe.get_doc(doc_data)
			doc.flags.ignore_permissions = True
			doc.flags.ignore_links = True
			doc.insert()

	frappe.db.commit()
