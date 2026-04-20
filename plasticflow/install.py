import frappe


def after_install():
	_create_roles()
	_grant_desk_shell_permissions()


def _create_roles():
	required_roles = [
		"Sales Manager",
		"Sales User",
		"Finance Officer",
		"Stock Manager",
		"Driver",
		"Management",
		"Warehouse Dispatcher",
		"Finance User",
	]
	for role_name in required_roles:
		if not frappe.db.exists("Role", role_name):
			role = frappe.new_doc("Role")
			role.role_name = role_name
			role.desk_access = 1
			role.insert(ignore_permissions=True)


def _grant_desk_shell_permissions():
	"""Grant read access on core doctypes required to render the Desk shell.

	Without Page read, opening /app throws "No permission for Page" for any
	role that doesn't already inherit it from another assignment.
	"""
	shell_doctypes = ("Page",)
	roles = ("Sales User",)
	for parent in shell_doctypes:
		for role in roles:
			exists = frappe.db.exists(
				"Custom DocPerm",
				{"parent": parent, "role": role, "permlevel": 0},
			)
			if exists:
				continue
			frappe.get_doc(
				{
					"doctype": "Custom DocPerm",
					"parent": parent,
					"parenttype": "DocType",
					"parentfield": "permissions",
					"role": role,
					"permlevel": 0,
					"read": 1,
				}
			).insert(ignore_permissions=True)
