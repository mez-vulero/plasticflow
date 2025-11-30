from __future__ import annotations

import frappe
from frappe import _


def execute(filters=None):
    filters = filters or {}
    from_date = filters.get("from_date")
    to_date = filters.get("to_date")

    conditions = ["docstatus = 1"]
    params = {}
    if from_date:
        conditions.append("order_date >= %(from_date)s")
        params["from_date"] = from_date
    if to_date:
        conditions.append("order_date <= %(to_date)s")
        params["to_date"] = to_date

    where_clause = f"where {' and '.join(conditions)}" if conditions else ""

    rows = frappe.db.sql(
        f"""
        select order_date, sum(total_amount) as total_amount
        from `tabSales Order`
        {where_clause}
        group by order_date
        order by order_date
        """,
        params,
        as_dict=True,
    )

    columns = [
        {"label": _("Date"), "fieldname": "order_date", "fieldtype": "Date", "width": 150},
        {"label": _("Total Sales"), "fieldname": "total_amount", "fieldtype": "Currency", "width": 150},
    ]

    chart = {
        "data": {
            "labels": [row.order_date for row in rows],
            "datasets": [
                {
                    "name": _("Total Sales"),
                    "values": [float(row.total_amount or 0) for row in rows],
                }
            ],
        },
        "type": "line",
    }

    return columns, rows, None, chart
