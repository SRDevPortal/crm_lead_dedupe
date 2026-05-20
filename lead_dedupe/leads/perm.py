# apps/lead_dedupe/lead_dedupe/leads/perm.py
import frappe

ARCHIVE_VIEW_ROLES = {"System Manager", "CRM Manager", "Sales Manager"}

def pqc_crm_lead(user, doctype=None):
    if user == "Administrator":
        return None

    if ARCHIVE_VIEW_ROLES.intersection(frappe.get_roles(user)):
        return None

    return "coalesce(`tabCRM Lead`.`sr_is_archived`, 0) = 0"

def crm_lead_has_permission(doc, ptype, user):
    # Let reads/listing happen
    if ptype in ("read", "print", "report"):
        return True
    # Block edits on archived leads (view-only)
    if getattr(doc, "sr_is_archived", 0):
        return False
    # Fall back to standard role permissions for non-archived
    return None
