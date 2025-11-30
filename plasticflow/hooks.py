app_name = "plasticflow"
app_title = "PlasticFlow"
app_publisher = "VuleroTech"
app_description = "End-to-end plastic raw material import and distribution workflow"
app_email = "mezmure.dawit@vulero.et"
app_license = "mit"
app_logo_url = "/assets/plasticflow/icons/plasticflow-icon.svg"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
add_to_apps_screen = [
	{
		"name": "plasticflow",
		"logo": "/assets/plasticflow/icons/plasticflow-icon.svg",
		"title": "PlasticFlow",
		"route": "/app",
		"has_permission": None,
	}
]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/plasticflow/css/plasticflow.css"
app_include_js = "/assets/plasticflow/js/pwa.js"
app_include_head_html = [
	"plasticflow/public/includes/theme_color.html",
]

# include js, css files in header of web template
# web_include_css = "/assets/plasticflow/css/plasticflow.css"
# web_include_js = "/assets/plasticflow/js/plasticflow.js"

website_manifest = "plasticflow/public/manifest.json"


doctype_js = {
	"Stock Entries": "public/js/stock_entry.js",
	"Number Card": "public/js/number_card.js",
	"Purchase Order": "public/js/purchase_order.js",
	"Import Shipment": "public/js/import_shipment.js",
	"Landing Cost Worksheet": "public/js/landing_cost_worksheet.js",
	"Sales Order": "public/js/sales_order.js",
}

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "plasticflow/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "plasticflow/public/icons.svg"

pwa = {
	"theme_color": "#f97316",
	"background_color": "#ffffff",
	"display": "standalone",
	"start_url": "/app",
	"scope": "/",
	"short_name": "PlasticFlow",
	"icons": [
		{
			"src": "/assets/plasticflow/pwa-icon-192.png",
			"sizes": "192x192",
			"type": "image/png",
		},
		{
			"src": "/assets/plasticflow/pwa-icon-512.png",
			"sizes": "512x512",
			"type": "image/png",
		},
	],
}

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "plasticflow.utils.jinja_methods",
# 	"filters": "plasticflow.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "plasticflow.install.before_install"
after_install = "plasticflow.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "plasticflow.uninstall.before_uninstall"
# after_uninstall = "plasticflow.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "plasticflow.utils.before_app_install"
# after_app_install = "plasticflow.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "plasticflow.utils.before_app_uninstall"
# after_app_uninstall = "plasticflow.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "plasticflow.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Notification Log": {
		"after_insert": "plasticflow.notifications.push.handle_notification_log",
	}
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"plasticflow.tasks.all"
# 	],
# 	"daily": [
# 		"plasticflow.tasks.daily"
# 	],
# 	"hourly": [
# 		"plasticflow.tasks.hourly"
# 	],
# 	"weekly": [
# 		"plasticflow.tasks.weekly"
# 	],
# 	"monthly": [
# 		"plasticflow.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "plasticflow.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "plasticflow.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "plasticflow.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "plasticflow.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["plasticflow.utils.before_request"]
# after_request = ["plasticflow.utils.after_request"]

# Job Events
# ----------
# before_job = ["plasticflow.utils.before_job"]
# after_job = ["plasticflow.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"plasticflow.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }
