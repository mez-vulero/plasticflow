import frappe


OLD_DOCTYPES = {
    "Plasticflow Stock Entry": "Stock Entries",
    "Plasticflow Stock Entry Item": "Stock Entry Items",
}


def execute():
    for old, new in OLD_DOCTYPES.items():
        if frappe.db.exists("DocType", old) and not frappe.db.exists("DocType", new):
            frappe.rename_doc("DocType", old, new, force=True)

    # Update link field options and related metadata that reference the old doctypes
    replacements = [
        ("Plasticflow Stock Entry", "Stock Entries"),
        ("Plasticflow Stock Entry Item", "Stock Entry Items"),
    ]
    option_targets = [
        ("tabDocField", "options"),
        ("tabCustom Field", "options"),
        ("tabDocType Link", "link_doctype"),
    ]
    for old, new in replacements:
        for table, column in option_targets:
            frappe.db.sql(
                f"""
                update `{table}`
                set `{column}` = %(new)s
                where `{column}` = %(old)s
                """,
                {"old": old, "new": new},
            )
        frappe.db.sql(
            """
            update `tabProperty Setter`
            set value = %(new)s
            where property = 'options'
                and value = %(old)s
            """,
            {"old": old, "new": new},
        )

    # Rename custom DocField internal names if they still exist
    fieldnames = {
        "Customs Entry-plasticflow_stock_entry": "stock_entry",
        "Plasticflow Stock Ledger Entry-plasticflow_stock_entry": "stock_entry",
        "Stock Ledger Entry-plasticflow_stock_entry": "stock_entry",
    }
    for old_name, new_name in fieldnames.items():
        if frappe.db.exists("DocField", old_name):
            frappe.rename_doc("DocField", old_name, new_name, force=True)

    # Rename database columns where necessary
    if frappe.db.has_column("Customs Entry", "plasticflow_stock_entry"):
        frappe.db.sql_ddl(
            "alter table `tabCustoms Entry` rename column `plasticflow_stock_entry` to `stock_entry`"
        )
    for doctype in ("Plasticflow Stock Ledger Entry", "Stock Ledger Entry"):
        if frappe.db.has_column(doctype, "plasticflow_stock_entry"):
            frappe.db.sql_ddl(
                f"alter table `tab{doctype}` rename column `plasticflow_stock_entry` to `stock_entry`"
            )
