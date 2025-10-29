import frappe
from frappe.model.document import Document
from frappe.utils import nowdate


class GatePass(Document):
    """Authorizes release of goods from warehouse to logistics."""

    def validate(self):
        self._set_item_defaults()

    def before_submit(self):
        self.status = "Issued"
        if not self.driver:
            frappe.msgprint("Driver is not assigned; delivery note will remain pending assignment.")

    def on_submit(self):
        delivery_note = self._create_delivery_note()
        self.db_set("delivery_note", delivery_note.name)
        frappe.db.set_value(
            "Sales Order",
            self.sales_order,
            {"delivery_note": delivery_note.name, "status": "Completed"},
        )

    def on_cancel(self):
        self.db_set("status", "Cancelled")
        if self.delivery_note:
            dn = frappe.get_doc("Delivery Note", self.delivery_note)
            if dn.docstatus == 0:
                dn.delete(ignore_permissions=True)
            else:
                dn.cancel()
        if self.invoice and frappe.db.exists("Plasticflow Invoice", self.invoice):
            frappe.db.set_value(
                "Plasticflow Invoice", self.invoice, "gate_pass", None, update_modified=False
            )
        if self.sales_order and frappe.db.exists("Sales Order", self.sales_order):
            frappe.db.set_value(
                "Sales Order",
                self.sales_order,
                {"status": "Invoiced", "gate_pass": None, "delivery_note": None},
                update_modified=False,
            )
        frappe.db.set_value(
            "Gate Pass",
            self.name,
            {"invoice": None, "sales_order": None, "delivery_note": None},
            update_modified=False,
        )

    def _set_item_defaults(self):
        for item in self.items:
            if item.product and not item.product_name:
                item.product_name = frappe.db.get_value("Product", item.product, "product_name")

    def _create_delivery_note(self):
        delivery_note = frappe.new_doc("Delivery Note")
        delivery_note.sales_order = self.sales_order
        delivery_note.gate_pass = self.name
        delivery_note.driver = self.driver
        delivery_note.delivery_date = nowdate()
        delivery_note.status = "Draft"
        delivery_note.vehicle_plate = self.vehicle_plate

        for item in self.items:
            delivery_note.append(
                "items",
                {
                    "product": item.product,
                    "product_name": item.product_name,
                    "quantity": item.quantity,
                    "uom": item.uom,
                    "stock_entry_item": item.stock_entry_item,
                    "warehouse": item.warehouse or self.warehouse,
                },
            )

        delivery_note.insert(ignore_permissions=True)
        return delivery_note
