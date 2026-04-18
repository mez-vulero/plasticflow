import json
import os

import frappe


def execute():
	"""Re-import Sales Dashboard workspace so the Landing Cost Calculator shortcut shows up."""

	workspace_name = "Sales Dashboard"
	json_path = os.path.join(
		frappe.get_app_path("plasticflow"),
		"plasticflow",
		"workspace",
		"sales_dashboard",
		"sales_dashboard.json",
	)

	if not os.path.isfile(json_path):
		return

	if frappe.db.exists("Workspace", workspace_name):
		frappe.db.sql(
			"update `tabUser` set default_workspace = NULL where default_workspace = %s",
			(workspace_name,),
		)
		frappe.db.delete("Has Role", {"parent": workspace_name, "parenttype": "Workspace"})
		frappe.db.delete("Workspace Link", {"parent": workspace_name, "parenttype": "Workspace"})
		frappe.db.delete("Workspace Shortcut", {"parent": workspace_name, "parenttype": "Workspace"})
		frappe.db.delete("Workspace Chart", {"parent": workspace_name, "parenttype": "Workspace"})
		frappe.db.delete("Workspace Number Card", {"parent": workspace_name, "parenttype": "Workspace"})
		frappe.db.delete("Workspace Quick List", {"parent": workspace_name, "parenttype": "Workspace"})
		frappe.db.delete("Workspace Custom Block", {"parent": workspace_name, "parenttype": "Workspace"})
		frappe.db.delete("Workspace", {"name": workspace_name})
		frappe.db.commit()

	with open(json_path) as f:
		doc_data = json.load(f)

	doc_data["doctype"] = "Workspace"
	doc = frappe.get_doc(doc_data)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_links = True
	doc.flags.ignore_mandatory = True
	doc.insert()

	frappe.db.commit()
	frappe.clear_cache()
