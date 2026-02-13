import json

import frappe


def _ensure_shortcut(content_list, shortcut_name):
	for block in content_list:
		if block.get("type") == "shortcut" and block.get("data", {}).get("shortcut_name") == shortcut_name:
			return
	content_list.append(
		{
			"id": "shortcut_stock_balance",
			"type": "shortcut",
			"data": {"shortcut_name": shortcut_name, "col": 3},
		}
	)


def execute():
	if not frappe.db.exists("Workspace", "Store Dashboard"):
		return

	workspace = frappe.get_doc("Workspace", "Store Dashboard")

	# Update shortcuts list
	has_shortcut = False
	for row in workspace.shortcuts or []:
		if row.label == "Stock Balance":
			has_shortcut = True
			break
	if not has_shortcut:
		workspace.append(
			"shortcuts",
			{
				"label": "Stock Balance",
				"type": "Report",
				"link_to": "Stock Balance",
				"report_ref_doctype": "Stock Ledger Entry",
			},
		)

	# Update workspace content JSON
	try:
		content_list = json.loads(workspace.content or "[]")
	except Exception:
		content_list = []

	_ensure_shortcut(content_list, "Stock Balance")
	workspace.content = json.dumps(content_list, separators=(",", ":"))

	workspace.save(ignore_permissions=True)
