# apps/lead_dedupe/lead_dedupe/leads/dup_utils.py

import re
import frappe

def norm_mobile(raw: str | None) -> str:
    """Normalize to last 10 digits (India-style)."""
    if not raw:
        return ""
    digits = re.sub(r"\D", "", raw)
    return digits[-10:] if len(digits) >= 10 else digits

def find_dup_candidates(
    mobile_norm: str,
    exclude_name: str | None = None,
    limit: int = 50,
):
    """Return possible dup rows with the same normalized mobile, newest first."""
    if not mobile_norm:
        return []
    rows = frappe.get_all(
        "CRM Lead",
        filters={"sr_mobile_norm": mobile_norm},
        fields=["name", "lead_name", "mobile_no", "sr_lead_pipeline", "status", "creation"],
        order_by="creation desc",
        limit=limit,
    )
    if exclude_name:
        rows = [r for r in rows if r["name"] != exclude_name]
    return rows

def score_duplicate(doc, cand) -> float:
    """Simple score: same normalized mobile is enough, other fields add confidence."""
    s = 70.0
    if (doc.get("lead_name") or "").strip() and (cand.get("lead_name") or "").strip():
        if doc.lead_name.strip().lower() == cand.lead_name.strip().lower():
            s += 20
    if doc.get("status") and cand.get("status") and doc.status == cand.status:
        s += 10
    if doc.get("sr_lead_pipeline") and cand.get("sr_lead_pipeline") \
       and doc.sr_lead_pipeline == cand.sr_lead_pipeline:
        s += 10
    return min(s, 100.0)

# ------------------------------
# NEW: recompute hit counts util
# ------------------------------

def recompute_hit_counts(mobile_norm: str):
    """
    Recalculate sr_dup_hit_count for *every* lead in the mobile group.
    """
    if not mobile_norm:
        return

    names = frappe.get_all(
        "CRM Lead",
        filters={"sr_mobile_norm": mobile_norm},
        pluck="name",
        order_by="creation desc",
    )

    updates = []
    for name in names:
        cands = find_dup_candidates(mobile_norm, exclude_name=name)
        updates.append({
            "doctype": "CRM Lead",
            "name": name,
            "fieldname": "sr_dup_hit_count",
            "value": len(cands),
        })

    if not updates:
        return

    try:
        frappe.db.bulk_update(doc_updates=updates, update_modified=False)
    except Exception:
        for u in updates:
            frappe.db.set_value(
                u["doctype"], u["name"], u["fieldname"], u["value"],
                update_modified=False
            )
