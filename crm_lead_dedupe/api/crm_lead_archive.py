import frappe
from crm_lead_dedupe.logging import log_operation
from crm_lead_dedupe.settings import is_enabled
from crm_lead_dedupe.leads.dup_utils import norm_mobile, sync_duplicate_group
from crm_lead_dedupe.leads.perm import require_dedupe_manager

@frappe.whitelist()
def backfill_archive_mobile_pipeline_groups():
    require_dedupe_manager()
    if not is_enabled("archive"):
        log_operation("backfill_archive_groups.skipped", reason="archive_disabled")
        return {"groups": 0, "skipped": "archive_disabled"}
    log_operation("backfill_archive_groups.start")
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
    log_operation("backfill_archive_groups.done", group_count=len(groups))
    return {"groups": len(groups)}

def _archive_group(mobile_norm: str | None):
    """Backward-compatible wrapper for older callers."""
    if not is_enabled("archive"):
        log_operation("archive_group.skipped", mobile_norm=mobile_norm, reason="archive_disabled")
        return
    log_operation("archive_group.start", mobile_norm=mobile_norm)
    sync_duplicate_group(mobile_norm)
    log_operation("archive_group.done", mobile_norm=mobile_norm)

@frappe.whitelist()
def archive_group_for_mobile_pipeline(mobile: str | None = None, pipeline: str | None = None):
    require_dedupe_manager()
    if not is_enabled("archive"):
        log_operation("archive_group_for_mobile_pipeline.skipped", mobile=mobile, pipeline=pipeline, reason="archive_disabled")
        return "skipped"
    log_operation("archive_group_for_mobile_pipeline.start", mobile=mobile, pipeline=pipeline)
    sync_duplicate_group(mobile, pipeline)
    frappe.db.commit()
    log_operation("archive_group_for_mobile_pipeline.done", mobile=mobile, pipeline=pipeline)
    return "ok"

def archive_group_for_doc(doc, method=None):
    """Hook target: sync old and new duplicate groups for this lead."""
    if not is_enabled("hooks"):
        log_operation("archive_group_for_doc.skipped", lead_name=doc.name, method=method, reason="hooks_disabled")
        return
    log_operation("archive_group_for_doc.start", lead_name=doc.name, method=method)
    old_group_key = getattr(doc.flags, "crm_lead_dedupe_old_group_key", None)
    if old_group_key:
        log_operation("archive_group_for_doc.old_group", lead_name=doc.name, old_group_key=old_group_key)
        sync_duplicate_group(*old_group_key)

    mobile_norm = getattr(doc, "sr_mobile_norm", None) or norm_mobile(getattr(doc, "mobile_no", ""))
    pipeline = getattr(doc, "sr_lead_pipeline", None)
    sync_duplicate_group(
        mobile_norm,
        pipeline,
        mark_unseen_for_primary=bool(getattr(doc.flags, "crm_lead_dedupe_mark_unseen_hit", False)),
    )
    log_operation("archive_group_for_doc.done", lead_name=doc.name, mobile_norm=mobile_norm, pipeline=pipeline)
