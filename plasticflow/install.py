import frappe


def after_install():
	_create_roles()


def _create_roles():
	required_roles = [
		"Sales Manager",
		"Finance Officer",
		"Stock Manager",
		"Driver",
		"Management",
	]
	for role_name in required_roles:
		if not frappe.db.exists("Role", role_name):
			role = frappe.new_doc("Role")
			role.role_name = role_name
			role.desk_access = 1
			role.insert(ignore_permissions=True)
