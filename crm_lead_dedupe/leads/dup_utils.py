import re
import frappe
from frappe.utils import cint, now_datetime
from crm_lead_dedupe.logging import log_operation


DT = "CRM Lead"
DUPLICATE_OF_FIELD = "sr_duplicate_of_name"
LEGACY_DUPLICATE_OF_FIELD = "sr_duplicate_of"
DUPLICATE_THRESHOLD = 80.0
OPTIONAL_CANDIDATE_FIELDS = ("sr_lead_pipeline", "sr_lead_platform", "source")
GROUP_STATE_FIELDS = (
    "converted",
    "sr_is_archived",
    "lead_owner",
    "_assign",
    "sr_dup_unseen_hit",
    "sr_dup_unseen_hit_on",
)


def norm_mobile(raw: str | None) -> str:
    """Normalize to last 10 digits (India-style)."""
    if not raw:
        return ""
    digits = re.sub(r"\D", "", raw)
    return digits[-10:] if len(digits) >= 10 else digits


def _has_column(fieldname: str) -> bool:
    try:
        return frappe.db.has_column(DT, fieldname)
    except Exception:
        return False


def _lead_fields(extra: list[str] | None = None) -> list[str]:
    fields = ["name", "lead_name", "mobile_no", "status", "creation"]
    for fieldname in OPTIONAL_CANDIDATE_FIELDS:
        if _has_column(fieldname):
            fields.append(fieldname)
    for fieldname in extra or []:
        if fieldname not in fields and _has_column(fieldname):
            fields.append(fieldname)
    return fields


def duplicate_filters(mobile_norm: str, pipeline: str | None = None) -> dict:
    # Mobile number is the single duplicate key. Pipeline is accepted only for
    # backward-compatible callers and is intentionally ignored.
    return {"sr_mobile_norm": mobile_norm}


def find_dup_candidates(
    mobile_norm: str,
    exclude_name: str | None = None,
    limit: int = 50,
    pipeline: str | None = None,
):
    """Return possible duplicate rows, newest first."""
    if not mobile_norm:
        return []
    rows = frappe.get_all(
        DT,
        filters=duplicate_filters(mobile_norm, pipeline),
        fields=_lead_fields(),
        order_by="creation desc",
        limit=limit,
    )
    if exclude_name:
        rows = [r for r in rows if r["name"] != exclude_name]
    return rows


def _value(row, fieldname: str):
    if hasattr(row, "get"):
        return row.get(fieldname)
    return getattr(row, fieldname, None)


def score_duplicate(doc, cand) -> float:
    """Score duplicate confidence by normalized mobile only."""
    doc_mobile = _value(doc, "sr_mobile_norm") or norm_mobile(_value(doc, "mobile_no"))
    cand_mobile = _value(cand, "sr_mobile_norm") or norm_mobile(_value(cand, "mobile_no"))
    if not doc_mobile or doc_mobile != cand_mobile:
        return 0.0
    return 100.0


def is_duplicate_match(doc, cand, threshold: float = DUPLICATE_THRESHOLD) -> bool:
    return score_duplicate(doc, cand) >= threshold


def is_active_lead_row(row) -> bool:
    return not cint(_value(row, "converted")) and not cint(_value(row, "sr_is_archived"))


def has_working_assignment(row) -> bool:
    if _value(row, "lead_owner"):
        return True

    assigned = _value(row, "_assign")
    if not assigned:
        return False
    if isinstance(assigned, list):
        return bool(assigned)

    try:
        assigned = frappe.parse_json(assigned)
    except Exception:
        assigned = str(assigned).strip()

    if isinstance(assigned, list):
        return bool(assigned)
    return bool(assigned and assigned != "[]")


def select_primary_row(rows):
    """
    Primary selection rules:
    1. Active assigned working lead wins. If many exist, keep the oldest one.
    2. If no active assigned lead exists, newest active lead wins.
    3. Converted/archived rows do not win while any active row exists.
    4. If every row is inactive, fall back to newest row for linkage only.
    """
    if not rows:
        return None

    active_rows = [row for row in rows if is_active_lead_row(row)]
    assigned_rows = [row for row in active_rows if has_working_assignment(row)]
    if assigned_rows:
        return sorted(assigned_rows, key=lambda row: _value(row, "creation") or "")[0]
    if active_rows:
        return active_rows[0]
    return rows[0]


def get_primary_lead_name_for_mobile(mobile_norm: str, pipeline: str | None = None) -> str | None:
    """Return the active primary CRM Lead name for a normalized mobile group."""
    if not mobile_norm:
        return None

    rows = frappe.get_all(
        DT,
        filters=duplicate_filters(mobile_norm, pipeline),
        fields=_lead_fields(["sr_mobile_norm", *GROUP_STATE_FIELDS]),
        order_by="creation desc",
    )
    primary = select_primary_row(rows)
    return primary.get("name") if primary else None


def get_primary_lead_name_for_lead(lead_name: str) -> str | None:
    """Resolve any CRM Lead name to its current duplicate-group primary."""
    if not lead_name or not frappe.db.exists(DT, lead_name):
        return None

    row = frappe.db.get_value(
        DT,
        lead_name,
        _lead_fields(["sr_mobile_norm", *GROUP_STATE_FIELDS]),
        as_dict=True,
    )
    if not row:
        return None

    mobile_norm = row.get("sr_mobile_norm") or norm_mobile(row.get("mobile_no"))
    if not mobile_norm:
        return lead_name

    return get_primary_lead_name_for_mobile(mobile_norm, row.get("sr_lead_pipeline")) or lead_name


def _candidate_json(candidates) -> str | None:
    if not candidates:
        return None
    try:
        return frappe.as_json(candidates[:5])
    except Exception:
        return None


def _bulk_update(doc_updates: dict[str, dict]):
    if not doc_updates:
        return

    try:
        frappe.db.bulk_update(DT, doc_updates, update_modified=False)
    except Exception:
        for name, values in doc_updates.items():
            frappe.db.set_value(DT, name, values, update_modified=False)


def _duplicate_link_values(value: str | None = None) -> dict:
    values = {DUPLICATE_OF_FIELD: value}
    if _has_column(LEGACY_DUPLICATE_OF_FIELD):
        values[LEGACY_DUPLICATE_OF_FIELD] = None
    return values


def sync_duplicate_group(
    mobile_norm: str,
    pipeline: str | None = None,
    mark_unseen_for_primary: bool = False,
):
    """Recompute archive, duplicate flags, and hit counts for a duplicate group."""
    if not mobile_norm:
        log_operation("sync_duplicate_group.skipped", reason="missing_mobile_norm", pipeline=pipeline)
        return

    log_operation(
        "sync_duplicate_group.start",
        mobile_norm=mobile_norm,
        pipeline=pipeline,
        mark_unseen_for_primary=mark_unseen_for_primary,
    )
    rows = frappe.get_all(
        DT,
        filters=duplicate_filters(mobile_norm, pipeline),
        fields=_lead_fields(["sr_mobile_norm", *GROUP_STATE_FIELDS]),
        order_by="creation desc",
    )
    if not rows:
        log_operation("sync_duplicate_group.done", mobile_norm=mobile_norm, pipeline=pipeline, row_count=0)
        return

    updates = {}
    relink_to_primary = []

    primary = select_primary_row(rows)
    primary_name = primary["name"]
    primary_is_active = is_active_lead_row(primary)
    has_unseen_flag = _has_column("sr_dup_unseen_hit")
    has_unseen_on = _has_column("sr_dup_unseen_hit_on")

    for row in rows:
        candidates = [
            r for r in rows
            if r["name"] != row["name"] and is_duplicate_match(row, r)
        ]
        values = {
            "sr_dup_hit_count": len(candidates),
            "sr_dup_candidates_json": _candidate_json(candidates),
        }

        if row["name"] == primary_name:
            values.update(
                {
                    "sr_is_archived": 0 if primary_is_active else cint(row.get("sr_is_archived")),
                    "sr_is_duplicate": 0,
                    **_duplicate_link_values(),
                    "sr_duplicate_score": 0,
                }
            )
            if has_unseen_flag:
                if not candidates:
                    values["sr_dup_unseen_hit"] = 0
                    if has_unseen_on:
                        values["sr_dup_unseen_hit_on"] = None
                elif mark_unseen_for_primary:
                    values["sr_dup_unseen_hit"] = 1
                    if has_unseen_on:
                        values["sr_dup_unseen_hit_on"] = now_datetime()
        else:
            score = score_duplicate(row, primary)
            matched = score >= DUPLICATE_THRESHOLD
            if matched:
                relink_to_primary.append(row["name"])
            values.update(
                {
                    "sr_is_archived": 1 if matched else 0,
                    "sr_is_duplicate": 1 if matched else 0,
                    **_duplicate_link_values(primary_name if matched else None),
                    "sr_duplicate_score": score,
                }
            )
            if has_unseen_flag:
                values["sr_dup_unseen_hit"] = 0
                if has_unseen_on:
                    values["sr_dup_unseen_hit_on"] = None

        updates[row["name"]] = values

    _bulk_update(updates)
    log_operation(
        "sync_duplicate_group.updated",
        mobile_norm=mobile_norm,
        pipeline=pipeline,
        row_count=len(rows),
        primary=primary_name,
        relink_count=len(relink_to_primary),
    )
    if relink_to_primary:
        try:
            from crm_lead_dedupe.integrations.wa_chat_hub import relink_crm_lead_conversations

            relink_crm_lead_conversations(primary_name, relink_to_primary)
            log_operation(
                "sync_duplicate_group.relinked_chat",
                mobile_norm=mobile_norm,
                primary=primary_name,
                relink_count=len(relink_to_primary),
            )
        except Exception:
            frappe.log_error(frappe.get_traceback(), "WA Chat Hub Lead Relink Failed")
            log_operation(
                "sync_duplicate_group.relink_chat_failed",
                mobile_norm=mobile_norm,
                primary=primary_name,
                relink_count=len(relink_to_primary),
            )


def recompute_hit_counts(mobile_norm: str):
    """
    Recalculate sr_dup_hit_count for *every* lead in the mobile group.
    """
    if not mobile_norm:
        return

    names = frappe.get_all(
        DT,
        filters={"sr_mobile_norm": mobile_norm},
        pluck="name",
        order_by="creation desc",
    )

    updates = {}
    for name in names:
        row = frappe.db.get_value(DT, name, _lead_fields(["sr_mobile_norm"]), as_dict=True)
        if not row:
            continue
        cands = [
            cand for cand in find_dup_candidates(mobile_norm, exclude_name=name)
            if score_duplicate(row, cand) >= DUPLICATE_THRESHOLD
        ]
        updates[name] = {"sr_dup_hit_count": len(cands)}

    _bulk_update(updates)
