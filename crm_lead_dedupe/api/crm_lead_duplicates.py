# apps/crm_lead_dedupe/crm_lead_dedupe/api/crm_lead_duplicates.py
import frappe
from crm_lead_dedupe.leads.dup_utils import norm_mobile, find_dup_candidates, score_duplicate

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


@frappe.whitelist()
def get_hit_counts_for_crm_leads(lead_names):
    names = _as_list(lead_names)
    if not names:
        return {"success": True, "result": {}}

    rows = frappe.get_all(
        "CRM Lead",
        filters={"name": ["in", names]},
        fields=["name", "mobile_no", "sr_mobile_norm"],
        limit_page_length=0,
    )

    result = {name: {"hit_count": 0} for name in names}
    for row in rows:
        mobile_norm = row.sr_mobile_norm or norm_mobile(row.mobile_no)
        if not mobile_norm:
            continue

        hit_count = frappe.db.count(
            "CRM Lead",
            {
                "sr_mobile_norm": mobile_norm,
                "name": ["!=", row.name],
            },
        )
        result[row.name] = {"hit_count": hit_count}

    return {"success": True, "result": result}


def _as_list(value):
    if isinstance(value, str):
        try:
            value = frappe.parse_json(value)
        except Exception:
            value = [value]
    if not isinstance(value, list):
        return []
    return [item.get("name") if isinstance(item, dict) else item for item in value if item]

