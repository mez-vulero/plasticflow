### PlasticFlow

PET stock and sales workflow

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch main
bench install-app plasticflow
```

After installation, install the additional Python requirements used for PWA push notifications:

```bash
bench pip install pywebpush py-vapid cairosvg
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
