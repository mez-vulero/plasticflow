import frappe


_ENABLE_KEY = "plasticflow_enable_fifo"
_DISABLE_KEY = "plasticflow_disable_fifo"


def is_fifo_enabled() -> bool:
	"""Return True when FIFO enforcement/allocation should be active."""
	# Hard-disable FIFO temporarily. Re-enable by restoring config-driven logic.
	return False
