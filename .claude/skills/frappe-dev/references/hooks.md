# hooks.py — Complete Reference

## Full hooks.py Template

```python
# apps/myapp/myapp/hooks.py

app_name = "myapp"
app_title = "My App"
app_publisher = "Your Company"
app_description = "Description"
app_email = "dev@yourcompany.com"
app_license = "MIT"
app_version = "0.0.1"

# ── UI Assets ────────────────────────────────────────────────────────────────
# Injected into ALL Desk pages
app_include_js = ["/assets/myapp/js/myapp.js"]
app_include_css = ["/assets/myapp/css/myapp.css"]

# Injected into web (non-Desk) pages
web_include_js = ["/assets/myapp/js/web.js"]
web_include_css = ["/assets/myapp/css/web.css"]

# ── DocType Events ────────────────────────────────────────────────────────────
doc_events = {
    "Sales Invoice": {
        "validate":    "myapp.events.on_validate",
        "on_submit":   "myapp.events.on_submit",
        "on_cancel":   "myapp.events.on_cancel",
        "before_save": "myapp.events.before_save",
        "after_insert":"myapp.events.after_insert",
        "on_trash":    "myapp.events.on_trash",
    },
    "*": {
        # Runs for every DocType
        "after_insert": "myapp.events.global_after_insert"
    }
}
# Event handler signature: def handler(doc, method=None): ...

# ── Scheduled Jobs ────────────────────────────────────────────────────────────
scheduler_events = {
    "all":          ["myapp.tasks.run_all"],           # every 60 seconds
    "hourly":       ["myapp.tasks.run_hourly"],
    "hourly_long":  ["myapp.tasks.long_hourly"],
    "daily":        ["myapp.tasks.run_daily"],
    "daily_long":   ["myapp.tasks.long_daily"],
    "weekly":       ["myapp.tasks.run_weekly"],
    "monthly":      ["myapp.tasks.run_monthly"],
    "cron": {
        "0 9 * * 1-5": ["myapp.tasks.weekday_morning"],  # cron syntax
        "*/30 * * * *": ["myapp.tasks.every_30_min"],
    }
}

# ── Fixtures ─────────────────────────────────────────────────────────────────
# Exported with `bench export-fixtures`, imported on `bench migrate`
fixtures = [
    "Role",
    "Workflow",
    "Print Format",
    "Custom Field",
    "Property Setter",
    "Notification",
    {"dt": "Custom Field", "filters": [["module", "=", "My App"]]},
    {"dt": "Client Script",  "filters": [["module", "=", "My App"]]},
]

# ── Override / Extend ─────────────────────────────────────────────────────────
# Override a whitelisted method entirely
override_whitelisted_methods = {
    "frappe.client.get_count": "myapp.overrides.custom_get_count"
}

# Extend (not replace) a DocType class
extend_doctype_class = {
    "ToDo": "myapp.overrides.CustomToDo"
}

# Override DocType class entirely
override_doctype_class = {
    "Sales Order": "myapp.overrides.CustomSalesOrder"
}

# ── Permissions ───────────────────────────────────────────────────────────────
has_permission = {
    "Event": "myapp.permissions.has_permission"
}

permission_query_conditions = {
    "Event": "myapp.permissions.get_permission_query_conditions"
}

# ── Installation Hooks ────────────────────────────────────────────────────────
before_install = "myapp.install.before_install"
after_install = "myapp.install.after_install"
before_uninstall = "myapp.install.before_uninstall"
after_uninstall = "myapp.install.after_uninstall"
after_migrate = "myapp.install.after_migrate"  # runs after bench migrate

# ── Portal / Web Pages ────────────────────────────────────────────────────────
website_route_rules = [
    {"from_route": "/books/<name>", "to_route": "book"},
]

# ── Email / Notifications ─────────────────────────────────────────────────────
standard_queries = {
    "Customer": "myapp.queries.customer_query"
}

# ── Jinja Environment ─────────────────────────────────────────────────────────
jinja = {
    "methods": ["myapp.jinja.get_context_data"],
    "filters": ["myapp.jinja.format_currency"]
}
```

---

## Scheduler Tasks Pattern

```python
# myapp/tasks.py
import frappe

def run_daily():
    """Runs every day. Must be idempotent."""
    frappe.db.auto_commit_on_many_writes = True
    try:
        for site_doc in frappe.get_all("My Config", {"active": 1}):
            process_site(site_doc.name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Daily Task Error")

def process_site(name):
    doc = frappe.get_doc("My Config", name)
    # ... do work ...
    frappe.db.commit()
```

---

## Background Jobs (Enqueue)

```python
from frappe.utils.background_jobs import enqueue

# Enqueue a long-running job
enqueue(
    method="myapp.tasks.heavy_task",
    queue="long",           # "default", "short", "long"
    timeout=600,            # seconds
    job_name="heavy_task_001",
    # kwargs passed to the method:
    doc_name="INV-001",
    extra_param="value"
)

# From a controller — queue_action
doc.queue_action("send_email", recipients=["a@b.com"])
```

---

## Override DocType Class Pattern

```python
# myapp/overrides.py
from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice

class CustomSalesInvoice(SalesInvoice):
    def validate(self):
        super().validate()
        self.custom_validate()

    def custom_validate(self):
        if self.custom_field and not self.customer:
            frappe.throw("Customer required when custom_field is set")
```

```python
# hooks.py
override_doctype_class = {
    "Sales Invoice": "myapp.overrides.CustomSalesInvoice"
}
```

---

## Permission Query Conditions

Filter list view results based on user:

```python
# myapp/permissions.py
import frappe

def get_permission_query_conditions(user):
    if not user:
        user = frappe.session.user
    if "Administrator" in frappe.get_roles(user):
        return ""
    return f"`tabEvent`.owner = {frappe.db.escape(user)}"

def has_permission(doc, user=None, permission_type=None):
    if permission_type == "read" and doc.is_public:
        return True
    if doc.owner == (user or frappe.session.user):
        return True
    return False
```
