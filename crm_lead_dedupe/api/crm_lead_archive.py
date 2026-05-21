import frappe
from crm_lead_dedupe.leads.dup_utils import norm_mobile, sync_duplicate_group
from crm_lead_dedupe.leads.perm import require_dedupe_manager

@frappe.whitelist()
def backfill_archive_mobile_pipeline_groups():
    require_dedupe_manager()
    pipeline_column = "sr_lead_pipeline" if frappe.db.has_column("CRM Lead", "sr_lead_pipeline") else "''"
    groups = frappe.db.sql(
        f"""
        select sr_mobile_norm, {pipeline_column} as sr_lead_pipeline
        from `tabCRM Lead`
        where ifnull(sr_mobile_norm,'')!=''
        group by sr_mobile_norm, {pipeline_column}
        """,
        as_dict=True,
    )

    for g in groups:
        sync_duplicate_group(g.sr_mobile_norm, g.get("sr_lead_pipeline"))

    frappe.db.commit()
    return {"groups": len(groups)}

def _archive_group(mobile_norm: str | None):
    """Backward-compatible wrapper for older callers."""
    sync_duplicate_group(mobile_norm)

@frappe.whitelist()
def archive_group_for_mobile_pipeline(mobile: str | None = None, pipeline: str | None = None):
    require_dedupe_manager()
    sync_duplicate_group(mobile, pipeline)
    frappe.db.commit()
    return "ok"

def archive_group_for_doc(doc, method=None):
    """Hook target: sync old and new duplicate groups for this lead."""
    old_group_key = getattr(doc.flags, "crm_lead_dedupe_old_group_key", None)
    if old_group_key:
        sync_duplicate_group(*old_group_key)

    mobile_norm = getattr(doc, "sr_mobile_norm", None) or norm_mobile(getattr(doc, "mobile_no", ""))
    pipeline = getattr(doc, "sr_lead_pipeline", None)
    sync_duplicate_group(
        mobile_norm,
        pipeline,
        mark_unseen_for_primary=bool(getattr(doc.flags, "crm_lead_dedupe_mark_unseen_hit", False)),
    )
