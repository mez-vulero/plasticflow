# REST API & Whitelisted Methods

## Auto-generated REST Endpoints

Every DocType gets automatic REST endpoints:

```
GET    /api/resource/{DocType}              → list
POST   /api/resource/{DocType}              → create
GET    /api/resource/{DocType}/{name}       → get one
PUT    /api/resource/{DocType}/{name}       → update
DELETE /api/resource/{DocType}/{name}       → delete
```

Example:
```bash
# Get list with filters
curl -X GET "http://site/api/resource/Customer?filters=[[\"customer_group\",\"=\",\"Retail\"]]" \
  -H "Authorization: token api_key:api_secret"

# Get single document
curl "http://site/api/resource/Customer/CUST-001" -H "Authorization: token api_key:api_secret"

# Create
curl -X POST "http://site/api/resource/Customer" \
  -H "Authorization: token api_key:api_secret" \
  -H "Content-Type: application/json" \
  -d '{"customer_name": "John Doe", "customer_type": "Individual"}'
```

---

## Custom Whitelisted Methods

```python
import frappe

@frappe.whitelist()
def get_customer_summary(customer_name):
    """POST /api/method/myapp.api.get_customer_summary"""
    doc = frappe.get_doc("Customer", customer_name)
    invoices = frappe.get_list("Sales Invoice",
        filters={"customer": customer_name, "docstatus": 1},
        fields=["name", "grand_total", "posting_date"]
    )
    return {
        "customer": doc.as_dict(),
        "invoices": invoices,
        "total": sum(i.grand_total for i in invoices)
    }

@frappe.whitelist(allow_guest=True)
def public_data():
    """Accessible without authentication"""
    return {"version": frappe.__version__}

@frappe.whitelist(methods=["POST"])
def create_order(data):
    """Only POST allowed"""
    data = frappe.parse_json(data)
    # ...
```

---

## Authentication Methods

1. **Session cookie** — default when using Frappe Desk
2. **API Key + Secret** (token auth):
   ```
   Authorization: token {api_key}:{api_secret}
   ```
3. **Bearer token** (OAuth2)

Generate API keys: User → API Access → Generate Keys

---

## Frappe Client Python SDK

```python
from frappe.client import FrappeClient

client = FrappeClient("https://mysite.example.com")
client.authenticate("admin@example.com", "password")

# or token auth
client = FrappeClient("https://mysite.example.com",
    api_key="xxx", api_secret="yyy")

docs = client.get_list("Customer", filters={"disabled": 0})
doc = client.get_doc("Customer", "CUST-001")
new = client.insert({"doctype": "Customer", "customer_name": "Jane"})
client.update({"doctype": "Customer", "name": "CUST-001", "mobile_no": "123"})
```

---
---
# Permissions Reference

## Permission Levels

| Level | Description |
|-------|-------------|
| 0 | Document-level (read/write/create/delete/submit/cancel/amend) |
| 1–9 | Field-level (set `permlevel` on field to restrict visibility/edit) |

## Role Permissions

Set in DocType permissions table. Key flags:
- `read` / `write` / `create` / `delete`
- `submit` / `cancel` / `amend` (submittable docs only)
- `report` — can see reports
- `export` — can export to CSV
- `import` — can import
- `share` — can share with others
- `print` — can print
- `email` — can send by email
- `if_owner` — restrict to docs owned by user

## Programmatic Permission Checks

```python
# Check permission
frappe.has_permission("Item", "write")
frappe.has_permission("Item", "write", doc=doc)

# Throw if no permission
frappe.has_permission("Item", "write", throw=True)

# Get roles
frappe.get_roles()                    # current user
frappe.get_roles("user@example.com")  # specific user

# Check role
"System Manager" in frappe.get_roles()

# Share with user
frappe.share.add("Customer", "CUST-001", "user@example.com",
    read=1, write=1, share=1)

# Get all users with access
frappe.share.get_users("Customer", "CUST-001")
```

## User Permission (field-level data isolation)

User Permissions restrict which linked documents a user can see.

```python
# Create a user permission
frappe.get_doc({
    "doctype": "User Permission",
    "user": "sales@example.com",
    "allow": "Territory",
    "for_value": "North America",
    "apply_to_all_doctypes": 1
}).insert(ignore_permissions=True)
```

---
---
# Setup & Environment Reference

## Installation Options

### Option 1: Easy Install Script (Linux/Mac)
```bash
pip install frappe-bench
bench init frappe-bench --frappe-branch version-15
cd frappe-bench
bench new-site mysite.localhost
bench --site mysite.localhost install-app frappe
bench start
```

### Option 2: Docker (Recommended for Production)
```bash
git clone https://github.com/frappe/frappe_docker
cd frappe_docker
cp example.env .env
docker compose -f compose.yaml \
  -f overrides/compose.mariadb.yaml \
  -f overrides/compose.redis.yaml up -d
```

### Option 3: DevContainer (VS Code — Recommended for Dev)
1. Install VS Code + Docker Desktop
2. Clone: `git clone https://github.com/frappe/frappe_docker`
3. Open in VS Code → "Reopen in Container"
4. Wait for container build (~3 min)
5. `bench new-site mysite.localhost && bench start`

## Developer Mode

```bash
# Enable
bench --site mysite.localhost set-config developer_mode 1
bench --site mysite.localhost clear-cache

# Or in site_config.json
{"developer_mode": 1}
```

Required so that DocType changes via Desk UI are written to JSON files in your app.

## Common bench Commands

```bash
bench start                                   # start all services
bench --site <site> migrate                   # run migrations + fixtures
bench --site <site> clear-cache               # clear redis cache
bench --site <site> clear-website-cache       # clear web cache
bench build --app myapp                       # bundle assets
bench watch                                   # auto-rebuild assets
bench --site <site> console                   # Python REPL
bench --site <site> mariadb                   # DB CLI
bench --site <site> backup                    # backup site
bench --site <site> restore <file.sql.gz>     # restore
bench --site <site> set-admin-password <pwd>  # reset admin pass
bench update --pull                           # update all apps
bench switch-to-branch version-15 frappe erpnext  # switch branches
bench get-app <git-url>                       # add app from git
bench get-app <git-url> --branch develop      # specific branch
bench --site <site> uninstall-app myapp       # uninstall
bench remove-app myapp                        # delete app
```

## App Directory Structure

```
myapp/
├── hooks.py                    # integration with frappe
├── patches.txt                 # migration patches list
├── setup.py
├── requirements.txt            # Python dependencies
├── myapp/
│   ├── __init__.py
│   ├── config/
│   │   ├── desktop.py          # module icons on Desk home
│   │   └── docs.py
│   ├── module_name/
│   │   ├── __init__.py
│   │   ├── doctype/
│   │   │   └── my_doctype/
│   │   │       ├── my_doctype.json  # schema
│   │   │       ├── my_doctype.py   # controller
│   │   │       ├── my_doctype.js   # form script
│   │   │       └── test_my_doctype.py
│   │   ├── page/               # custom Desk pages
│   │   ├── report/             # reports
│   │   └── web_form/           # public web forms
│   ├── templates/
│   │   └── pages/              # Jinja web pages (www/ route)
│   ├── www/                    # static + Python web pages
│   │   ├── mypage.html
│   │   └── mypage.py
│   └── public/
│       ├── js/
│       └── css/
└── frontend/                   # optional frappe-ui SPA
    ├── src/
    └── package.json
```

## Patches (Data Migrations)

```python
# myapp/patches/v1_0/my_patch.py
import frappe

def execute():
    """Run once on bench migrate — must be idempotent"""
    frappe.db.sql("""
        UPDATE `tabItem` SET status = 'Active'
        WHERE status IS NULL
    """)
    frappe.db.commit()
```

Add to `patches.txt`:
```
myapp.patches.v1_0.my_patch
```
