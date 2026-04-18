# DocTypes — Complete Reference

## Field Types

| fieldtype | Description | Notes |
|-----------|-------------|-------|
| `Data` | Short text string | |
| `Text` | Long text (textarea) | |
| `Small Text` | Medium textarea | |
| `Text Editor` | Rich text (Quill) | |
| `Markdown Editor` | Markdown input | |
| `Int` | Integer | |
| `Float` | Decimal number | |
| `Currency` | Monetary value | Uses system currency |
| `Percent` | 0–100 float | |
| `Check` | Boolean (0/1) | |
| `Date` | Date picker | |
| `Datetime` | Date + time | |
| `Time` | Time picker | |
| `Select` | Dropdown | options: "A\nB\nC" |
| `Link` | Foreign key to another DocType | options: "DocType Name" |
| `Dynamic Link` | Link where DocType is from another field | |
| `Table` | Child table (another DocType) | options: "Child DocType" |
| `Table MultiSelect` | Multi-row child without naming | |
| `Attach` | File attachment | |
| `Attach Image` | Image attachment | |
| `Signature` | Signature pad | |
| `Geolocation` | JSON geo data | |
| `Color` | Color picker | |
| `Rating` | Star rating (1–5) | |
| `Password` | Masked input | |
| `Read Only` | Display only | |
| `HTML` | Static HTML in form | |
| `Section Break` | Divides form into sections | |
| `Column Break` | Creates multi-column layout | |
| `Tab Break` | Creates tabbed layout | |
| `Heading` | Bold label in form | |
| `Button` | Clickable button in form | |
| `Code` | Code editor | |
| `Autocomplete` | Text with suggestions | |
| `Phone` | Phone number | |
| `Duration` | Duration picker | |

---

## DocType JSON Structure (minimal example)

```json
{
  "doctype": "DocType",
  "name": "Book",
  "module": "Library Management",
  "is_submittable": 0,
  "track_changes": 1,
  "fields": [
    {
      "fieldname": "title",
      "fieldtype": "Data",
      "label": "Title",
      "reqd": 1,
      "in_list_view": 1
    },
    {
      "fieldname": "author",
      "fieldtype": "Link",
      "label": "Author",
      "options": "Author"
    },
    {
      "fieldname": "section_break_1",
      "fieldtype": "Section Break",
      "label": "Details"
    },
    {
      "fieldname": "description",
      "fieldtype": "Text Editor",
      "label": "Description"
    },
    {
      "fieldname": "items",
      "fieldtype": "Table",
      "label": "Items",
      "options": "Book Item"
    }
  ],
  "permissions": [
    {
      "role": "Librarian",
      "read": 1,
      "write": 1,
      "create": 1,
      "delete": 1
    }
  ]
}
```

---

## Controller Lifecycle — All Hooks

```python
class MyDoc(Document):
    # --- Insert ---
    def before_insert(self): ...
    def after_insert(self): ...

    # --- Save (insert + update) ---
    def validate(self): ...           # runs before every save
    def before_save(self): ...
    def on_update(self): ...          # after save
    def after_update_after_submit(self): ...  # edit after submission

    # --- Submit/Cancel (submittable only) ---
    def before_submit(self): ...
    def on_submit(self): ...
    def before_cancel(self): ...
    def on_cancel(self): ...

    # --- Trash ---
    def on_trash(self): ...
    def after_delete(self): ...

    # --- Load ---
    def onload(self): ...             # runs every time form loads in browser
    def before_load(self): ...

    # --- Rename ---
    def after_rename(self, old_name, new_name, merge=False): ...
```

---

## Naming Series

In the DocType JSON, set `autoname`:

```json
{
  "autoname": "naming_series:",    // uses Naming Series field
  "autoname": "BOOK-.####",        // BOOK-0001, BOOK-0002 ...
  "autoname": "field:email",       // use value of 'email' field as name
  "autoname": "hash",              // random hash
  "autoname": "Prompt"             // user enters name manually
}
```

---

## Child / Table DocType

Child DocTypes have `istable = 1` in JSON. They cannot be saved independently.

```python
# Append a row to child table
doc.append("items", {
    "item_code": "ITEM-001",
    "qty": 5,
    "rate": 100
})
doc.save()

# Iterate child rows
for row in doc.items:
    print(row.item_code, row.qty)

# Access child row by locals (in JS/form events)
# frappe.model.set_value(cdt, cdn, 'fieldname', value)
```

---

## Single DocType

Used for settings/config — one row, no list view. Set `issingle = 1`.

```python
# Read
val = frappe.db.get_single_value("My Settings", "api_key")

# Write
settings = frappe.get_single("My Settings")
settings.api_key = "new_key"
settings.save()
```

---

## Virtual DocType

No database table — you control data source. Set `is_virtual = 1` and implement `get_list`, `get`, `insert`, `update`, `delete` controller methods.

```python
class VirtualDoc(Document):
    @staticmethod
    def get_list(args):
        # return list of dicts
        return [{"name": "001", "title": "First"}]

    @staticmethod
    def get(name):
        return {"name": name, "title": "Some Title"}
```

---

## Custom Fields (Programmatic)

Add during app install via `hooks.py` fixtures or:

```python
# In a migration script or patch
frappe.get_doc({
    "doctype": "Custom Field",
    "dt": "Sales Invoice",          # target DocType
    "fieldname": "my_custom_field",
    "label": "My Custom Field",
    "fieldtype": "Data",
    "insert_after": "customer"
}).insert(ignore_permissions=True)
```

Via fixtures in `hooks.py`:
```python
fixtures = [
    {"dt": "Custom Field", "filters": [["module", "=", "My App"]]}
]
```
Then `bench export-fixtures` to export, and they auto-import on `bench migrate`.

---

## Property Setters

Override existing DocType field properties without touching core:

```python
frappe.make_property_setter({
    "doctype": "Sales Invoice",
    "fieldname": "customer",
    "property": "reqd",
    "value": "1",
    "property_type": "Check"
})
```

---

## frappe.db API (Python)

```python
# Get single value
frappe.db.get_value("Customer", "CUST-001", "customer_name")
frappe.db.get_value("Customer", {"mobile_no": "123"}, ["name", "customer_name"])

# Get list
frappe.db.get_list("Item", filters={"disabled": 0}, fields=["name", "item_name"])
frappe.db.get_all("Item")  # bypasses permissions

# Exists
frappe.db.exists("Customer", "CUST-001")  # returns name or None
frappe.db.exists("Customer", {"email": "a@b.com"})

# Set value (direct DB, no hooks)
frappe.db.set_value("Item", "ITEM-001", "rate", 200)
frappe.db.set_value("Item", "ITEM-001", {"rate": 200, "description": "Updated"})

# SQL (avoid when possible)
results = frappe.db.sql("""
    SELECT name, item_name FROM `tabItem`
    WHERE item_group = %(group)s
""", {"group": "Electronics"}, as_dict=True)

# Count
frappe.db.count("Item", {"disabled": 0})

# Commit / rollback (usually auto)
frappe.db.commit()
frappe.db.rollback()
```
