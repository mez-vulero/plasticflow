---
name: frappe-dev
description: >
  Expert knowledge for building custom Frappe Framework apps, DocTypes, controllers, hooks, 
  Jinja templates, REST APIs, Frappe UI components, and ERPNext customizations. Use this skill 
  whenever the user mentions Frappe, ERPNext, bench, DocType, frappe.get_doc, hooks.py, 
  Frappe Desk, frappe-ui, custom app development, whitelisted methods, form scripts, or any 
  ERPNext/Frappe-specific development concept. Always trigger for questions about Frappe 
  app scaffolding, customization of standard doctypes, client-side frappe.js APIs, 
  frappe-ui Vue components, permissions, scheduler events, or bench CLI commands.
---

# Frappe Framework Development Skill

Frappe is a full-stack, batteries-included web framework (Python + JavaScript + MariaDB) that 
powers ERPNext. Everything is built around **DocTypes** — metadata-driven data models that 
auto-generate database tables, REST APIs, and Desk forms.

## Quick Reference Index

- **App Scaffolding & Setup** → see below + `references/setup.md`
- **DocTypes & Controllers (Python)** → `references/doctypes.md`
- **Hooks System** → `references/hooks.md`
- **Frappe Desk JS API** → `references/js-api.md`
- **Frappe UI (Vue 3 component lib)** → `references/frappe-ui.md`
- **REST API & Whitelisted Methods** → `references/rest-api.md`
- **Permissions & Roles** → `references/permissions.md`

---

## 1. Architecture Mental Model

```
bench/                          ← workspace managed by bench CLI
├── apps/
│   ├── frappe/                 ← core framework
│   ├── erpnext/                ← ERP app (optional)
│   └── myapp/                  ← YOUR custom app
│       ├── hooks.py            ← integration points into framework
│       ├── myapp/
│       │   ├── module_name/
│       │   │   └── doctype/
│       │   │       └── my_doctype/
│       │   │           ├── my_doctype.json    ← schema definition
│       │   │           ├── my_doctype.py      ← controller
│       │   │           └── my_doctype.js      ← form script
│       │   └── templates/
│       └── setup.py
└── sites/
    └── mysite.localhost/
```

Key concept: **meta-data is data**. DocType JSON files ARE the schema — Frappe reads them to 
create/alter MariaDB tables automatically on `bench migrate`.

---

## 2. App Scaffolding (Quick Start)

```bash
# Install bench and create environment
pip install frappe-bench
bench init frappe-bench --frappe-branch version-15
cd frappe-bench

# Create a site
bench new-site mysite.localhost --db-name mydb

# Create your app
bench new-app myapp
# → prompts for title, description, publisher, email, icon

# Install app on site
bench --site mysite.localhost install-app myapp

# Enable developer mode (required for editing DocTypes in code)
bench --site mysite.localhost set-config developer_mode 1
bench --site mysite.localhost clear-cache

# Start dev server
bench start
```

App folder created at `apps/myapp/myapp/`. Read `references/setup.md` for Docker & DevContainer setup.

---

## 3. DocType Basics

DocTypes define data models. Created via Desk UI (when developer mode is on, JSON is exported to app folder) or by writing JSON directly.

```python
# apps/myapp/myapp/module/doctype/book/book.py
import frappe
from frappe.model.document import Document

class Book(Document):
    # Controller lifecycle hooks — define as methods
    def before_insert(self):
        pass

    def validate(self):
        if not self.title:
            frappe.throw("Title is required")

    def on_submit(self):
        self.notify_members()

    def notify_members(self):
        # custom method callable via frappe.get_doc('Book', name).notify_members()
        pass
```

**Key controller lifecycle order:**
`before_insert` → `validate` → `before_save` → `on_update` / `after_insert` → `on_submit` → `on_cancel`

Read `references/doctypes.md` for field types, child tables, naming series, single doctypes, virtual doctypes, and full lifecycle reference.

---

## 4. hooks.py — Integration Points

`hooks.py` is the app's configuration hub. It wires your code into framework events.

```python
# apps/myapp/myapp/hooks.py  (representative selection)

app_name = "myapp"
app_title = "My App"

# Run code on DocType events without modifying the DocType controller
doc_events = {
    "Sales Invoice": {
        "on_submit": "myapp.events.sales_invoice.on_submit",
        "on_cancel": "myapp.events.sales_invoice.on_cancel",
    },
    "*": {
        "after_insert": "myapp.events.all_docs.log_insert"
    }
}

# Expose Python functions as REST endpoints
# (also done with @frappe.whitelist() decorator)
override_whitelisted_methods = {
    "frappe.client.get_count": "myapp.api.custom_get_count"
}

# Scheduled background jobs
scheduler_events = {
    "daily": ["myapp.tasks.daily_sync"],
    "hourly": ["myapp.tasks.hourly_check"],
    "cron": {
        "0 9 * * 1-5": ["myapp.tasks.weekday_morning"]
    }
}

# Inject JS/CSS into Desk
app_include_js = ["/assets/myapp/js/custom.js"]
app_include_css = ["/assets/myapp/css/custom.css"]

# Add fixtures (exported config that travels with the app)
fixtures = [
    "Custom Field",
    {"dt": "Property Setter", "filters": [["doc_type", "in", ["Sales Invoice"]]]},
    "Print Format",
    "Role",
]
```

Read `references/hooks.md` for the complete hooks reference.

---

## 5. Whitelisted Methods (Server-Side API)

```python
# myapp/api.py
import frappe

@frappe.whitelist()
def get_items(category):
    """Callable via /api/method/myapp.api.get_items"""
    return frappe.get_list("Item",
        filters={"item_group": category},
        fields=["name", "item_name", "rate"],
        order_by="item_name asc"
    )

@frappe.whitelist(allow_guest=True)
def public_endpoint(data):
    """Accessible without login"""
    return {"status": "ok"}
```

Call from JS:
```javascript
frappe.call({
    method: 'myapp.api.get_items',
    args: { category: 'Electronics' },
    callback: (r) => console.log(r.message)
});
```

---

## 6. Form Scripts (Client-Side JS)

```javascript
// myapp/module/doctype/book/book.js
frappe.ui.form.on('Book', {
    // Fires when form loads
    refresh(frm) {
        if (frm.doc.status === 'Published') {
            frm.add_custom_button('Send to Library', () => {
                frappe.call({
                    method: 'myapp.api.send_to_library',
                    args: { book: frm.doc.name },
                    callback: (r) => frappe.msgprint(r.message)
                });
            }, 'Actions'); // group button under "Actions"
        }
    },

    // Field trigger — fires when field value changes
    author(frm) {
        if (frm.doc.author) {
            frappe.db.get_value('Author', frm.doc.author, 'email')
                .then(r => frm.set_value('author_email', r.message.email));
        }
    },

    // Child table row trigger
    'items.qty': function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        frappe.model.set_value(cdt, cdn, 'amount', row.qty * row.rate);
    }
});
```

Read `references/js-api.md` for the full Desk JS API (frappe.db, frappe.model, frappe.ui, dialogs, controls).

---

## 7. frappe-ui (Modern Vue 3 Components)

Used for standalone SPAs (not Desk forms). E.g., Frappe Cloud, CRM, Gameplan frontends.

```bash
npm install frappe-ui
```

```vue
<!-- App.vue -->
<script setup>
import { Button, Dialog, createResource } from 'frappe-ui'

const items = createResource({
  url: 'myapp.api.get_items',
  params: { category: 'Electronics' },
  auto: true
})
</script>

<template>
  <Button variant="solid" @click="items.reload()">Refresh</Button>
  <div v-if="items.loading">Loading...</div>
  <div v-for="item in items.data" :key="item.name">{{ item.item_name }}</div>
</template>
```

Read `references/frappe-ui.md` for all components: Button, Dialog, ListView, FormControl, Badge, Tooltip, Avatar, Tabs, DataTable, and the `createResource` / `createListResource` composables.

---

## 8. Common frappe Python API Snippets

```python
import frappe

# CRUD
doc = frappe.get_doc("Item", "ITEM-001")           # fetch
doc.description = "Updated"
doc.save()

new_doc = frappe.get_doc({"doctype": "Item", "item_name": "New"})
new_doc.insert(ignore_permissions=True)

frappe.db.set_value("Item", "ITEM-001", "rate", 500)  # direct DB update (no hooks)

# Query
rows = frappe.get_list("Item",
    filters={"item_group": "Products", "disabled": 0},
    fields=["name", "item_name", "rate"],
    order_by="creation desc",
    limit=50
)

frappe.get_all("Item", filters={"rate": [">", 100]})  # ignores permissions

# Single value
val = frappe.db.get_value("Customer", "CUST-001", "customer_name")

# Error handling
frappe.throw("Something went wrong", frappe.ValidationError)
frappe.msgprint("FYI message", alert=True)

# Session
frappe.session.user        # current user email
frappe.get_roles()         # roles of current user
frappe.has_permission("Item", "write")

# Cache
frappe.cache.set_value("my_key", data, expires_in_sec=300)
frappe.cache.get_value("my_key")
```

---

## 9. Bench CLI Cheatsheet

```bash
bench new-app <appname>                          # scaffold new app
bench --site <site> install-app <app>            # install app on site
bench --site <site> migrate                      # run DB migrations + reload fixtures
bench --site <site> clear-cache                  # clear redis cache
bench --site <site> console                      # Python REPL with frappe context
bench --site <site> execute myapp.tasks.run      # run a Python function
bench build --app myapp                          # bundle frontend assets
bench watch                                      # watch + rebuild assets on change
bench restart                                    # restart workers
bench update --pull                              # update all apps
bench get-app <git-url>                          # add existing app from git
```

---

## 10. Best Practices

- Always use `doc.save()` over `frappe.db.set_value()` unless you explicitly want to bypass hooks/validation
- Add `ignore_permissions=True` to `insert()`/`save()` only in background jobs, never in user-facing code
- Prefer `frappe.get_list()` over raw SQL — it respects permissions; use `frappe.get_all()` only when intentionally bypassing them
- Use `fixtures` in `hooks.py` to export Custom Fields, Property Setters, and Print Formats with your app
- Enable `developer_mode` on dev site so DocType changes sync to JSON files in your app
- Use `bench migrate` after every DocType JSON change
- Store business logic in controller methods, not in form scripts — JS is for UX only
- For cross-DocType side effects, prefer `doc_events` in `hooks.py` over modifying core DocType controllers

---

## When to read reference files

| Task | Read |
|------|------|
| Field types, naming, child tables, single/virtual doctypes | `references/doctypes.md` |
| Complete hooks list, scheduler, fixtures, overrides | `references/hooks.md` |
| frappe.db, frappe.model, frm.* JS APIs, Dialogs | `references/js-api.md` |
| frappe-ui Vue 3 components & createResource | `references/frappe-ui.md` |
| REST API, OAuth, guest access | `references/rest-api.md` |
| Roles, permissions, share, has_permission | `references/permissions.md` |
| Docker / DevContainers / production setup | `references/setup.md` |
