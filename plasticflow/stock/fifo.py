import frappe


_ENABLE_KEY = "plasticflow_enable_fifo"
_DISABLE_KEY = "plasticflow_disable_fifo"


def is_fifo_enabled() -> bool:
	"""Return True when FIFO enforcement/allocation should be active."""
	if not hasattr(frappe, "conf"):
		return False
	if frappe.conf.get(_DISABLE_KEY) is not None:
		return not bool(frappe.conf.get(_DISABLE_KEY))
	return bool(frappe.conf.get(_ENABLE_KEY))
