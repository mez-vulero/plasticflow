### PlasticFlow

End-to-end plastics import, costing, stock, and sales management built on Frappe.

#### What the app does
- **Import & Customs Lifecycle**: Capture purchase orders, shipments, customs data, and automate stock entry creation as clearance statuses change.
- **Landed Cost Allocation**: Allocate multi-currency expenses (freight, duty, handling) to shipment items with exchange-rate tracking, locking, and audit history.
- **Stock Visibility**: Maintain customs vs. warehouse availability, reservations, and issues through a purpose-built ledger and Stock Entries doctype.
- **Sales & Delivery**: Reserve and issue stock through FIFO-aware sales orders, gate passes, and delivery notes with automated withholding and commission tracking.
- **Profitability Intelligence**: Roll up landed cost, revenue, and commission per shipment for P&L insights and dashboards.
- **Workspace UX**: Opinionated workspace with shortcuts, charts, and reports specific to plastics trading operations.

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch main
bench install-app plasticflow
```

#### Prerequisites
- Frappe/ERPNext bench environment running Python 3.11+ and Node 18+.
- MariaDB 10.6+ (recommended by Frappe).
- Redis server for background workers and caching.

#### Required Python libraries
PlasticFlow relies on a few extra libraries that are not bundled with core Frappe:

```bash
bench pip install pywebpush py-vapid cairosvg
```

If you use yarn-based asset builds, also ensure the following global npm packages are available:

```bash
bench setup requirements --node
```

After installing requirements, compile assets and run migrations:

```bash
bench migrate
bench build --apps plasticflow
bench restart
```

### Progressive Web App (PWA) Setup

PlasticFlow ships with a custom service worker and optional device push notifications. To enable push notifications:

1. Generate a VAPID key pair:
   ```bash
   bench execute plasticflow.notifications.push.generate_vapid_keys
   ```
   Copy the resulting `public_key` and `private_key` values.

2. Add the keys (and an optional contact email) to your site configuration:
   ```json
   {
     "plasticflow_vapid_public_key": "<public_key>",
     "plasticflow_vapid_private_key": "<private_key>",
     "plasticflow_vapid_email": "support@example.com"
   }
   ```

3. Apply database changes and rebuild assets:
   ```bash
   bench migrate
   bench build --apps plasticflow
   bench restart
   ```

4. In the browser, reload the Desk and allow the push permission prompt to store your subscription.

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/plasticflow
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade
### CI

This app can use GitHub Actions for CI. The following workflows are configured:

- CI: Installs this app and runs unit tests on every push to `develop` branch.
- Linters: Runs [Frappe Semgrep Rules](https://github.com/frappe/semgrep-rules) and [pip-audit](https://pypi.org/project/pip-audit/) on every pull request.


### License

mit
