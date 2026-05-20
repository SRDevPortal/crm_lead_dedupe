# apps/crm_lead_dedupe/crm_lead_dedupe/api/crm_lead_archive.py

import frappe
from crm_lead_dedupe.leads.dup_utils import norm_mobile, recompute_hit_counts   # same helper you use elsewhere

@frappe.whitelist()
def backfill_archive_mobile_pipeline_groups():
    groups = frappe.db.sql(
        """
        select sr_mobile_norm
        from `tabCRM Lead`
        where ifnull(sr_mobile_norm,'')!=''
        group by sr_mobile_norm
        """,
        as_dict=True,
    )

    for g in groups:
        _archive_group(g.sr_mobile_norm)
        recompute_hit_counts(g.sr_mobile_norm)

    frappe.db.commit()
    return {"groups": len(groups)}

def _archive_group(mobile_norm: str | None):
    """Keep newest (by creation desc) visible; archive the rest for this mobile group."""
    if not mobile_norm:
        return

    rows = frappe.get_all(
        "CRM Lead",
        filters={"sr_mobile_norm": mobile_norm},
        fields=["name", "creation"],
        order_by="creation desc",
    )
    if not rows:
        return

    newest = rows[0]["name"]
    for r in rows:
        frappe.db.set_value(
            "CRM Lead",
            r["name"],
            "sr_is_archived",
            0 if r["name"] == newest else 1,
            update_modified=False,
        )

@frappe.whitelist()
def archive_group_for_mobile_pipeline(mobile: str | None = None, pipeline: str | None = None):
    """Callable from JS if needed: pass normalized mobile. Pipeline is ignored."""
    _archive_group(mobile)
    if mobile:
        recompute_hit_counts(mobile)
    frappe.db.commit()
    return "ok"

def archive_group_for_doc(doc, method=None):
    """Hook target: call after_insert/on_update to archive older dups for THIS lead."""
    mobile_norm = getattr(doc, "sr_mobile_norm", None) or norm_mobile(getattr(doc, "mobile_no", ""))
    _archive_group(mobile_norm)
    if mobile_norm:
        recompute_hit_counts(mobile_norm)

