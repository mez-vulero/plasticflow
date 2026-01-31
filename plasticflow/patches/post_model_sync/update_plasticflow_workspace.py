import json
from pathlib import Path

import frappe


WORKSPACES = {
	"PlasticFlow": "plasticflow",
	"Sales Dashboard": "sales_dashboard",
}


CHILD_TABLE_FIELDS = [
    "links",
    "shortcuts",
    "charts",
    "number_cards",
    "custom_blocks",
    "quick_lists",
]


SIMPLE_FIELDS = [
    "app",
    "label",
    "module",
    "icon",
    "sequence_id",
    "for_user",
    "public",
    "restrict_to_domain",
    "title",
    "type",
    "content",
]


def execute():
	base_path = Path(frappe.get_app_path("plasticflow")) / "plasticflow" / "workspace"
	for workspace_name, folder in WORKSPACES.items():
		json_path = base_path / folder / f"{folder}.json"
		if not json_path.exists():
			continue

		data = json.loads(json_path.read_text())

		if frappe.db.exists("Workspace", workspace_name):
			ws = frappe.get_doc("Workspace", workspace_name)
		else:
			ws = frappe.new_doc("Workspace")
			ws.name = workspace_name

		for field in SIMPLE_FIELDS:
			if field in data:
				setattr(ws, field, data[field])

		for field in CHILD_TABLE_FIELDS:
			if not ws.meta.get_field(field):
				continue
			ws.set(field, [])
			for row in data.get(field, []):
				ws.append(field, row)

		ws.save(ignore_permissions=True)
