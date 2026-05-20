# apps/crm_lead_dedupe/crm_lead_dedupe/api/crm_lead_merge.py
import frappe
from frappe.model.rename_doc import rename_doc
from crm_lead_dedupe.leads.dup_utils import recompute_hit_counts

@frappe.whitelist()
def merge_crm_leads(primary: str, duplicates):
    # coercion from JSON/str
    if isinstance(duplicates, str):
        duplicates = [d.strip() for d in duplicates.split(",") if d.strip()]
    if not duplicates:
        frappe.throw("No duplicates provided.")

    # permission check on primary
    if not frappe.has_permission("CRM Lead", "write", primary):
        frappe.throw("Not permitted.", frappe.PermissionError)

    allowed_duplicates = []
    for d in duplicates:
        if d == primary:
            continue
        if not frappe.db.exists("CRM Lead", d):
            frappe.throw(f"Duplicate lead {d} does not exist.")
        if not frappe.has_permission("CRM Lead", "write", d):
            frappe.throw(f"Not permitted to merge {d}.", frappe.PermissionError)
        allowed_duplicates.append(d)

    if not allowed_duplicates:
        frappe.throw("No valid duplicates provided.")

    # merge each duplicate into primary
    for d in allowed_duplicates:
        rename_doc("CRM Lead", d, primary, force=True, merge=True)

    # primary must be clean (not a duplicate of anything)
    frappe.db.set_value(
        "CRM Lead",
        primary,
        {
            "sr_is_duplicate": 0,
            "sr_duplicate_of": None,
            "sr_duplicate_score": 0,
        },
        update_modified=False,
    )

    # refresh hit counts for this group so list shows correct pills
    m = frappe.db.get_value("CRM Lead", primary, "sr_mobile_norm")
    if m:
        recompute_hit_counts(m)

    frappe.db.commit()
    return {"status": "ok", "primary": primary, "merged": allowed_duplicates}

