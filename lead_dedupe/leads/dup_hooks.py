# apps/lead_dedupe/lead_dedupe/leads/dup_hooks.py

import json
import frappe
from .dup_utils import norm_mobile, find_dup_candidates, score_duplicate, recompute_hit_counts


# -------------------------
# Helpers
# -------------------------

def _is_newest_in_group(doc) -> bool:
    """True if this doc is the newest for the normalized mobile group."""
    if not getattr(doc, "sr_mobile_norm", None):
        return False
    newest = frappe.db.get_value(
        "CRM Lead",
        {"sr_mobile_norm": doc.sr_mobile_norm},
        "name",
        order_by="creation desc",
    )
    return newest == doc.name


def _mobile_changed(doc) -> bool:
    """Detect change in normalized mobile on updates."""
    if doc.is_new():
        return True
    old_mobile = frappe.db.get_value(doc.doctype, doc.name, "sr_mobile_norm")
    return old_mobile != doc.sr_mobile_norm


def _archive_older_dups(doc):
    """
    Archive older leads within the normalized mobile group.
    Keep newest un-archived.
    """
    if not doc.sr_mobile_norm:
        return

    rows = frappe.get_all(
        "CRM Lead",
        filters={"sr_mobile_norm": doc.sr_mobile_norm},
        fields=["name", "creation"],
        order_by="creation desc",
    )
    if not rows:
        return

    newest = rows[0]["name"]
    updates = [
        {
            "doctype": "CRM Lead",
            "name": r["name"],
            "fieldname": "sr_is_archived",
            "value": 0 if r["name"] == newest else 1,
        }
        for r in rows
    ]
    if not updates:
        return

    try:
        frappe.db.bulk_update(doc_updates=updates, update_modified=False)
    except Exception:
        for u in updates:
            frappe.db.set_value(
                u["doctype"], u["name"], u["fieldname"], u["value"], update_modified=False
            )


def _clear_dup_link(doc):
    """
    Clear sr_duplicate_of if:
      - it points to a non-existent record
      - it points to an archived record (hidden by PQC)
      - this doc is the newest (primary) in group
    Also set doc.flags.ignore_links = True when clearing to avoid LinkValidationError.
    """
    dup = (doc.get("sr_duplicate_of") or "").strip()
    if not dup:
        return

    # Target missing
    if not frappe.db.exists("CRM Lead", dup):
        # prevent link validation from firing before we clear it
        doc.flags.ignore_links = True
        doc.sr_duplicate_of = None
        doc.sr_is_duplicate = 0
        doc.sr_duplicate_score = 0
        return

    # Target archived (typically filtered by your PQC)
    if frappe.db.get_value("CRM Lead", dup, "sr_is_archived"):
        doc.flags.ignore_links = True
        doc.sr_duplicate_of = None
        doc.sr_is_duplicate = 0
        doc.sr_duplicate_score = 0
        return

    # Newest (primary) should never point to older
    if doc.name and _is_newest_in_group(doc):
        # not strictly necessary to skip validation here, because target exists,
        # but we clear it to keep the primary clean
        doc.sr_duplicate_of = None
        doc.sr_is_duplicate = 0
        doc.sr_duplicate_score = 0


# -------------------------
# Hooks
# -------------------------

def on_before_validate(doc, method=None):
    """
    Runs *before* Frappe link validation.
    Ensure mobile is normalized (used by _is_newest_in_group) and clear bad link.
    """
    # make sure normalization exists for the primary test
    doc.sr_mobile_norm = norm_mobile(doc.mobile_no or "")
    _clear_dup_link(doc)                 # clears bad sr_duplicate_of
    # sets doc.flags.ignore_links = True when needed to bypass validation
    frappe.logger().info(f"before_validate clearing check for {doc.name} dup={doc.get('sr_duplicate_of')}")


def on_validate(doc, method=None):
    """Runs before save; ensures stale links won't fail framework validation."""
    doc.sr_mobile_norm = norm_mobile(doc.mobile_no or "")
    _clear_dup_link(doc)


def on_before_save(doc, method=None):
    """
    - Normalize mobile
    - Find/score candidates with the same normalized mobile
    - Set duplicate flags on non-primary rows
    - Maintain JSON summary for quick debug
    - Archive older rows in group when mobile changes
    - Recompute hit counts for the entire group (so list pills are always fresh)
    """
    # Normalize mobile
    doc.sr_mobile_norm = norm_mobile(doc.mobile_no or "")

    # Find candidates (same normalized mobile, excluding self)
    cands = find_dup_candidates(doc.sr_mobile_norm, exclude_name=doc.name)

    # Score and pick best
    best, best_score = None, 0.0
    for c in cands:
        sc = score_duplicate(doc, c)
        if sc > best_score:
            best, best_score = c, sc

    # Primary (newest) should NOT be marked duplicate
    doc_is_primary = bool(doc.name) and _is_newest_in_group(doc)

    if not doc_is_primary and best and best_score >= 70:
        doc.sr_is_duplicate = 1
        doc.sr_duplicate_of = best["name"]
        doc.sr_duplicate_score = best_score
    else:
        doc.sr_is_duplicate = 0
        doc.sr_duplicate_of = None
        doc.sr_duplicate_score = best_score or 0

    # quick stats / debug
    doc.sr_dup_hit_count = len(cands)
    doc.sr_dup_candidates_json = None
    if cands:
        try:
            doc.sr_dup_candidates_json = json.dumps(cands[:5], default=str)
        except Exception:
            pass

    # archive if group changed
    if _mobile_changed(doc):
        _archive_older_dups(doc)

    # always refresh the group's hit counts so list shows correct pills
    if doc.sr_mobile_norm:
        recompute_hit_counts(doc.sr_mobile_norm)
