import frappe
from frappe import _
from frappe.model.document import Document


class CRMLeadDedupeSettings(Document):
    def validate(self):
        if self.crm_lead_dedupe_newest_primary_enabled and self.crm_lead_dedupe_oldest_primary_enabled:
            frappe.throw(
                _("Use Newest Lead As Primary and Use Old Lead As Primary cannot both be selected.")
            )
