app_name = "lead_dedupe"
app_title = "Lead Dedupe"
app_publisher = "Sriaas"
app_description = "Duplicate detection + merge for Lead"
app_email = "webdevelopersriaas@gmail.com"
app_license = "mit"

# Inject JS only for CRM Lead screens.
doctype_js = {"CRM Lead": "public/js/crm_lead_form.js"}
doctype_list_js = {"CRM Lead": "public/js/crm_lead_list.js"}

# Installation
# ------------

# before_install = "lead_dedupe.install.before_install"
after_install = "lead_dedupe.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "lead_dedupe.uninstall.before_uninstall"
# after_uninstall = "lead_dedupe.uninstall.after_uninstall"

# Run CFs at migrate
after_migrate = "lead_dedupe.install.after_migrate"

permission_query_conditions = {
    "CRM Lead": "lead_dedupe.leads.perm.pqc_crm_lead",
}

has_permission = {
    "CRM Lead": "lead_dedupe.leads.perm.crm_lead_has_permission",
}

# Compute dedupe on save
doc_events = {
    "CRM Lead": {
        # MUST run before link validation
        "before_validate": "lead_dedupe.leads.dup_hooks.on_before_validate",

        # safety net (some builds also run later checks)
        "validate":        "lead_dedupe.leads.dup_hooks.on_validate",

        "before_insert":   "lead_dedupe.leads.dup_hooks.on_before_save",
        "before_save":     "lead_dedupe.leads.dup_hooks.on_before_save",

        # your archive recompute (fine to keep)
        "after_insert":    "lead_dedupe.api.crm_lead_archive.archive_group_for_doc",
        "on_update":       "lead_dedupe.api.crm_lead_archive.archive_group_for_doc",
    }
}

# Patches
# Create lead_dedupe/patches.txt with the line below:
# lead_dedupe.patches.v15_add_mobile_pipeline_index

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "lead_dedupe",
# 		"logo": "/assets/lead_dedupe/logo.png",
# 		"title": "Lead Dedupe",
# 		"route": "/lead_dedupe",
# 		"has_permission": "lead_dedupe.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/lead_dedupe/css/lead_dedupe.css"
# app_include_js = "/assets/lead_dedupe/js/lead_dedupe.js"

# include js, css files in header of web template
# web_include_css = "/assets/lead_dedupe/css/lead_dedupe.css"
# web_include_js = "/assets/lead_dedupe/js/lead_dedupe.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "lead_dedupe/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "lead_dedupe/public/icons.svg"

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

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "lead_dedupe.utils.jinja_methods",
# 	"filters": "lead_dedupe.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "lead_dedupe.install.before_install"
# after_install = "lead_dedupe.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "lead_dedupe.uninstall.before_uninstall"
# after_uninstall = "lead_dedupe.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "lead_dedupe.utils.before_app_install"
# after_app_install = "lead_dedupe.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "lead_dedupe.utils.before_app_uninstall"
# after_app_uninstall = "lead_dedupe.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "lead_dedupe.notifications.get_notification_config"

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

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"lead_dedupe.tasks.all"
# 	],
# 	"daily": [
# 		"lead_dedupe.tasks.daily"
# 	],
# 	"hourly": [
# 		"lead_dedupe.tasks.hourly"
# 	],
# 	"weekly": [
# 		"lead_dedupe.tasks.weekly"
# 	],
# 	"monthly": [
# 		"lead_dedupe.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "lead_dedupe.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "lead_dedupe.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "lead_dedupe.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["lead_dedupe.utils.before_request"]
# after_request = ["lead_dedupe.utils.after_request"]

# Job Events
# ----------
# before_job = ["lead_dedupe.utils.before_job"]
# after_job = ["lead_dedupe.utils.after_job"]

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
# 	"lead_dedupe.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }
