app_name = "crm_lead_dedupe"
app_title = "CRM Lead Dedupe"
app_publisher = "SRIAAS"
app_description = "Duplicate detection + merge for Lead"
app_email = "webdevelopersriaas@gmail.com"
app_license = "mit"

required_apps = ["crm", "sriaas_clinic"]

# Installation
# before_install = "crm_lead_dedupe.install.before_install"
after_install = "crm_lead_dedupe.install.after_install"
after_migrate = "crm_lead_dedupe.install.after_migrate"

# Uninstallation
# before_uninstall = "crm_lead_dedupe.uninstall.before_uninstall"
# after_uninstall = "crm_lead_dedupe.uninstall.after_uninstall"

# Inject JS only for CRM Lead screens.
doctype_js = {"CRM Lead": "public/js/crm_lead_form.js"}
doctype_list_js = {"CRM Lead": "public/js/crm_lead_list.js"}

override_whitelisted_methods = {
    "crm.api.doc.get_data": "crm_lead_dedupe.api.crm_doc_guard.get_data",
}

permission_query_conditions = {
    "CRM Lead": "crm_lead_dedupe.leads.perm.pqc_crm_lead",
}

has_permission = {
    "CRM Lead": "crm_lead_dedupe.leads.perm.crm_lead_has_permission",
}

# Compute dedupe on save
doc_events = {
    "CRM Lead": {
        # Normalizes fields for app logic; link safety is handled by setup metadata.
        "before_validate": "crm_lead_dedupe.leads.dup_hooks.on_before_validate",

        # safety net (some builds also run later checks)
        "validate":        "crm_lead_dedupe.leads.dup_hooks.on_validate",

        "before_insert":   "crm_lead_dedupe.leads.dup_hooks.on_before_save",
        "before_save":     "crm_lead_dedupe.leads.dup_hooks.on_before_save",

        # your archive recompute (fine to keep)
        "after_insert":    "crm_lead_dedupe.api.crm_lead_archive.archive_group_for_doc",
        "on_update":       "crm_lead_dedupe.api.crm_lead_archive.archive_group_for_doc",
    }
}
