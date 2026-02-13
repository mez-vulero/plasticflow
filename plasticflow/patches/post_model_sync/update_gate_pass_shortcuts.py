import json

import frappe


def _update_workspace(workspace):
	changed = False

	# Update shortcuts rows
	for row in workspace.shortcuts or []:
		if row.label == "Gate Pass Requests":
			row.label = "Gate Passes"
			row.type = "DocType"
			row.link_to = "Gate Pass"
			row.report_ref_doctype = None
			changed = True
		if row.link_to == "Gate Pass Request":
			row.link_to = "Gate Pass"
			changed = True
		if row.report_ref_doctype == "Gate Pass Request":
			row.report_ref_doctype = "Gate Pass"
			changed = True

	# Update content JSON
	try:
		content_list = json.loads(workspace.content or "[]")
	except Exception:
		content_list = []

	if content_list:
		content_str = json.dumps(content_list)
		updated = content_str.replace("Gate Pass Requests", "Gate Passes").replace(
			"Gate Pass Request", "Gate Pass"
		)
		if updated != content_str:
			workspace.content = updated
			changed = True

	if changed:
		workspace.save(ignore_permissions=True)


def execute():
	for name in ("Sales Dashboard", "PlasticFlow", "Purchase Dashboard"):
		if frappe.db.exists("Workspace", name):
			workspace = frappe.get_doc("Workspace", name)
			_update_workspace(workspace)
