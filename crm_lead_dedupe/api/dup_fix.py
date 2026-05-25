import frappe
from frappe import _
from crm_lead_dedupe.logging import log_operation
from crm_lead_dedupe.settings import is_enabled
from crm_lead_dedupe.leads.dup_utils import DUPLICATE_OF_FIELD, LEGACY_DUPLICATE_OF_FIELD
from crm_lead_dedupe.leads.perm import can_manage_dedupe

def _is_newest(name: str) -> bool:
    d = frappe.get_doc("CRM Lead", name)
    if not d.get("sr_mobile_norm"):
        return False
    filters = {"sr_mobile_norm": d.sr_mobile_norm}
    if d.get("sr_lead_pipeline") and frappe.db.has_column("CRM Lead", "sr_lead_pipeline"):
        filters["sr_lead_pipeline"] = d.get("sr_lead_pipeline")
    newest = frappe.db.get_value(
        "CRM Lead",
        filters,
        "name",
        order_by="creation desc",
    )
    return newest == name

@frappe.whitelist()
def fix_duplicate_of_if_stale(name: str):
    """Clear sr_duplicate_of if target is missing, archived, or this row is the newest (primary)."""
    log_operation("fix_duplicate_of_if_stale.start", lead_name=name)
    if not is_enabled("hooks"):
        log_operation("fix_duplicate_of_if_stale.done", lead_name=name, skipped="hooks_disabled")
        return
    if not name or not frappe.db.exists("CRM Lead", name):
        log_operation("fix_duplicate_of_if_stale.done", lead_name=name, skipped="missing_lead")
        return
    if not can_manage_dedupe() and not frappe.has_permission("CRM Lead", "write", name):
        frappe.throw(_("Not permitted to fix duplicate metadata."), frappe.PermissionError)

    fields = [DUPLICATE_OF_FIELD]
    if frappe.db.has_column("CRM Lead", LEGACY_DUPLICATE_OF_FIELD):
        fields.append(LEGACY_DUPLICATE_OF_FIELD)
    row = frappe.db.get_value("CRM Lead", name, fields, as_dict=True) or {}
    dup = row.get(DUPLICATE_OF_FIELD) or row.get(LEGACY_DUPLICATE_OF_FIELD)
    if not dup:
        log_operation("fix_duplicate_of_if_stale.done", lead_name=name, skipped="no_duplicate_link")
        return

    clear = False
    if not frappe.db.exists("CRM Lead", dup):
        clear = True
    elif frappe.db.get_value("CRM Lead", dup, "sr_is_archived"):
        clear = True
    elif _is_newest(name):
        clear = True

    if clear:
        values = {
            DUPLICATE_OF_FIELD: None,
            "sr_is_duplicate": 0,
            "sr_duplicate_score": 0,
        }
        if frappe.db.has_column("CRM Lead", LEGACY_DUPLICATE_OF_FIELD):
            values[LEGACY_DUPLICATE_OF_FIELD] = None
        frappe.db.set_value("CRM Lead", name, values, update_modified=False)
        frappe.db.commit()
        log_operation("fix_duplicate_of_if_stale.cleared", lead_name=name, duplicate_of=dup)
    else:
        log_operation("fix_duplicate_of_if_stale.done", lead_name=name, duplicate_of=dup, skipped="still_valid")
