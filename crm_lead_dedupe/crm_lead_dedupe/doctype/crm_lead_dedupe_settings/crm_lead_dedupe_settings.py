import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class CRMLeadDedupeSettings(Document):
    def validate(self):
        if self.crm_lead_dedupe_newest_primary_enabled and self.crm_lead_dedupe_oldest_primary_enabled:
            frappe.throw(
                _("Use Newest Lead As Primary and Use Old Lead As Primary cannot both be selected.")
            )
        for fieldname in (
            "crm_lead_dedupe_delay_seconds",
            "crm_lead_dedupe_metadata_wait_seconds",
            "crm_lead_dedupe_failed_retry_seconds",
        ):
            if cint(self.get(fieldname)) < 0:
                frappe.throw(_("{0} cannot be negative.").format(self.meta.get_label(fieldname)))
