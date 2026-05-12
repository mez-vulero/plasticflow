import frappe

from plasticflow.stock import rebuild as stock_rebuild


def execute():
	"""Rebuild Stock Ledger Entry rollup from Stock Entry Items.

	The rollup cache had multiple write paths with different formulas, so
	historical drift accumulated. This patch makes the cache deterministic
	by overwriting every row from the canonical truth. Idempotent — safe
	to re-run if a discrepancy is reported.

	Stock Ledger Movement (the audit log) is intentionally not touched.
	"""
	if not frappe.db.table_exists("Stock Ledger Entry"):
		return
	rebuilt = stock_rebuild.rebuild_all(log_progress=False)
	frappe.db.commit()
	print(f"plasticflow: rebuilt {rebuilt} Stock Ledger Entry slots from canonical truth")
