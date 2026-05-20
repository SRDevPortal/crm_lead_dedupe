# apps/lead_dedupe/lead_dedupe/api/crm_lead_duplicates.py
import frappe
from lead_dedupe.leads.dup_utils import norm_mobile, find_dup_candidates, score_duplicate

def _summary(name: str) -> dict:
    """
    Fast, permission-agnostic fetch for just the fields we need in the modal.
    Using frappe.db.get_value bypasses PQC/permissions, so duplicates still show
    even if some are archived/hidden in the list.
    """
    row = frappe.db.get_value(
        "CRM Lead",
        name,
        [
            "name",
            "owner",
            "status",
            "sr_lead_disposition",
            "creation",
            "mobile_no",
            "lead_name",
            "sr_lead_platform",
            "source",
        ],
        as_dict=True,
    ) or {}

    return {
        "name": row.get("name"),
        "owner": row.get("owner"),
        "stage": row.get("sr_lead_disposition") or row.get("status"),
        "creation": row.get("creation"),
        "mobile_no": row.get("mobile_no"),
        "lead_name": row.get("lead_name"),
        "platform": row.get("sr_lead_platform"),
        "source": row.get("source"),
    }

@frappe.whitelist()
def get_duplicates_for_crm_lead(lead_name: str):
    """
    Duplicates by normalized mobile, excluding the primary.
    Returns columns: Lead Id, Owner, Stage, Creation, Mobile, Full Name,
    Platform, Source, Score.
    """
    if not lead_name:
        return []

    lead = frappe.get_doc("CRM Lead", lead_name)
    m = norm_mobile(lead.mobile_no or "")

    if not m:
        return []

    rows = []
    # find_dup_candidates should already return names for the same mobile
    for c in find_dup_candidates(m, exclude_name=lead.name, limit=50):
        s = score_duplicate(lead, c)
        r = _summary(c["name"])
        r["score"] = s if s is not None else 100
        rows.append(r)

    # Sort: higher score first, then newest first
    rows.sort(key=lambda x: (x.get("score", 0), x.get("creation") or ""), reverse=True)
    return rows
