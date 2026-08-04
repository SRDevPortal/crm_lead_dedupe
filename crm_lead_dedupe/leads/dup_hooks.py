from hashlib import sha256

import frappe
from frappe.utils import add_to_date, cint, now_datetime
from crm_lead_dedupe.logging import log_operation
from crm_lead_dedupe.settings import get_setting, is_enabled
from .dup_utils import (
    DUPLICATE_OF_FIELD,
    LEGACY_DUPLICATE_OF_FIELD,
    DEFAULT_BLOCKED_MOBILES,
    duplicate_filters,
    is_valid_auto_merge_mobile,
    norm_mobile,
)


# -------------------------
# Helpers
# -------------------------

def _is_newest_in_group(doc) -> bool:
    """True if this doc is the newest for the normalized mobile group."""
    if not getattr(doc, "sr_mobile_norm", None):
        return False
    filters = duplicate_filters(doc.sr_mobile_norm, doc.get("sr_lead_pipeline"))
    newest = frappe.db.get_value(
        "CRM Lead",
        filters,
        "name",
        order_by="creation desc",
    )
    return newest == doc.name


def _old_group_key(doc):
    if doc.is_new():
        return None

    fields = ["sr_mobile_norm"]
    if frappe.db.has_column(doc.doctype, "sr_lead_pipeline"):
        fields.append("sr_lead_pipeline")

    old = frappe.db.get_value(doc.doctype, doc.name, fields, as_dict=True)
    if not old or not old.get("sr_mobile_norm"):
        return None

    return (old.get("sr_mobile_norm"), old.get("sr_lead_pipeline"))


def _store_old_group_key(doc):
    old_key = _old_group_key(doc)
    current_key = (doc.sr_mobile_norm, doc.get("sr_lead_pipeline"))
    if old_key and old_key != current_key:
        doc.flags.crm_lead_dedupe_old_group_key = old_key
        return old_key
    return None


def _mark_pending_group(mobile_norm: str | None, pipeline: str | None = None):
    if not mobile_norm or not frappe.db.has_column("CRM Lead", "sr_dedupe_pending"):
        return
    filters = duplicate_filters(mobile_norm, pipeline)
    names = frappe.get_all("CRM Lead", filters=filters, pluck="name", limit_page_length=0)
    if not names:
        return
    now = now_datetime()
    delay = max(0, cint(get_setting("crm_lead_dedupe_delay_seconds")))
    values = {"sr_dedupe_pending": 1, "sr_dedupe_status": "Pending"}
    if frappe.db.has_column("CRM Lead", "sr_dedupe_stage"):
        values.update(
            {
                "sr_dedupe_stage": "Pending",
                "sr_dedupe_result": None,
                "sr_dedupe_queued_at": now,
                "sr_dedupe_not_before": add_to_date(now, seconds=delay),
                "sr_dedupe_started_at": None,
                "sr_dedupe_completed_at": None,
            }
        )
    frappe.db.bulk_update("CRM Lead", {name: values for name in names}, update_modified=False)


def _input_hash(doc) -> str:
    payload = "|".join(
        [
            doc.get("sr_mobile_norm") or "",
            doc.get("sr_lead_pipeline") or "",
            doc.get("source") or "",
        ]
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _metadata_missing(doc) -> list[str]:
    missing = []
    if cint(get_setting("crm_lead_dedupe_require_pipeline")) and not doc.get("sr_lead_pipeline"):
        missing.append("pipeline")
    if cint(get_setting("crm_lead_dedupe_require_source")) and not doc.get("source"):
        missing.append("source")
    return missing


def _mark_doc_pending(doc, *, force: bool = False):
    if not hasattr(doc, "sr_dedupe_pending"):
        return

    input_hash = _input_hash(doc)
    if not force and not doc.is_new() and doc.get("sr_dedupe_input_hash") == input_hash:
        return

    now = now_datetime()
    if is_valid_auto_merge_mobile(doc.sr_mobile_norm, DEFAULT_BLOCKED_MOBILES):
        doc.sr_dedupe_pending = 1
        if hasattr(doc, "sr_dedupe_status"):
            doc.sr_dedupe_status = "Pending"
        if hasattr(doc, "sr_dedupe_stage"):
            doc.sr_dedupe_stage = "Waiting for Metadata" if _metadata_missing(doc) else "Pending"
            doc.sr_dedupe_result = None
            doc.sr_dedupe_pipeline = doc.get("sr_lead_pipeline")
            doc.sr_dedupe_queued_at = now
            doc.sr_dedupe_not_before = add_to_date(
                now,
                seconds=max(0, cint(get_setting("crm_lead_dedupe_delay_seconds"))),
            )
            doc.sr_dedupe_started_at = None
            doc.sr_dedupe_completed_at = None
            doc.sr_dedupe_input_hash = input_hash
        if hasattr(doc, "sr_dedupe_error"):
            doc.sr_dedupe_error = None
    else:
        doc.sr_dedupe_pending = 0
        if hasattr(doc, "sr_dedupe_status"):
            doc.sr_dedupe_status = "Skipped"
        if hasattr(doc, "sr_dedupe_stage"):
            doc.sr_dedupe_stage = "Completed"
            doc.sr_dedupe_result = "Skipped"
            doc.sr_dedupe_pipeline = doc.get("sr_lead_pipeline")
            doc.sr_dedupe_queued_at = now
            doc.sr_dedupe_not_before = now
            doc.sr_dedupe_started_at = now
            doc.sr_dedupe_completed_at = now
            doc.sr_dedupe_input_hash = input_hash
        if hasattr(doc, "sr_dedupe_error"):
            doc.sr_dedupe_error = None


def _get_duplicate_of(doc) -> str:
    return (doc.get(DUPLICATE_OF_FIELD) or doc.get(LEGACY_DUPLICATE_OF_FIELD) or "").strip()


def _set_duplicate_of(doc, value: str | None = None):
    if hasattr(doc, DUPLICATE_OF_FIELD):
        doc.set(DUPLICATE_OF_FIELD, value)
    if hasattr(doc, LEGACY_DUPLICATE_OF_FIELD):
        doc.set(LEGACY_DUPLICATE_OF_FIELD, None)


def _clear_dup_link(doc):
    """
    Clear sr_duplicate_of if:
      - it points to a non-existent record
      - this doc is the newest (primary) in group
    """
    dup = _get_duplicate_of(doc)
    if not dup:
        return

    # Target missing
    if not frappe.db.exists("CRM Lead", dup):
        # prevent link validation from firing before we clear it
        doc.flags.ignore_links = True
        _set_duplicate_of(doc)
        doc.sr_is_duplicate = 0
        doc.sr_duplicate_score = 0
        return

    # Newest (primary) should never point to older
    if doc.name and _is_newest_in_group(doc):
        # not strictly necessary to skip validation here, because target exists,
        # but we clear it to keep the primary clean
        _set_duplicate_of(doc)
        doc.sr_is_duplicate = 0
        doc.sr_duplicate_score = 0


# -------------------------
# Hooks
# -------------------------

def on_before_validate(doc, method=None):
    """Normalize mobile early for controller and hook logic."""
    if not is_enabled("hooks"):
        log_operation("lead_before_validate.skipped", lead_name=doc.name, reason="hooks_disabled")
        return
    doc.sr_mobile_norm = norm_mobile(doc.mobile_no or "")
    _clear_dup_link(doc)
    log_operation("lead_before_validate", lead_name=doc.name, is_new=doc.is_new(), mobile_norm=doc.sr_mobile_norm)


def on_validate(doc, method=None):
    """Runs before save; ensures stale links won't fail framework validation."""
    if not is_enabled("hooks"):
        log_operation("lead_validate.skipped", lead_name=doc.name, reason="hooks_disabled")
        return
    doc.sr_mobile_norm = norm_mobile(doc.mobile_no or "")
    _clear_dup_link(doc)
    log_operation("lead_validate", lead_name=doc.name, is_new=doc.is_new(), mobile_norm=doc.sr_mobile_norm)


def on_before_save(doc, method=None):
    """
    Keep Lead saves cheap. The delayed worker performs duplicate lookup and
    optional merge after the Lead transaction is complete.
    """
    if not is_enabled("hooks"):
        log_operation("lead_before_save.skipped", lead_name=doc.name, reason="hooks_disabled")
        return

    doc.sr_mobile_norm = norm_mobile(doc.mobile_no or "")
    old_key = _store_old_group_key(doc)
    if old_key:
        _mark_pending_group(old_key[0], old_key[1])

    if (
        not getattr(frappe.flags, "crm_lead_dedupe_scheduler", False)
        and not getattr(doc.flags, "crm_lead_dedupe_state_queued", False)
    ):
        _mark_doc_pending(doc, force=bool(doc.is_new() or old_key))
        doc.flags.crm_lead_dedupe_state_queued = True

    doc.flags.crm_lead_dedupe_mark_unseen_hit = bool(
        doc.sr_mobile_norm and (doc.is_new() or old_key)
    )

    log_operation(
        "lead_before_save",
        lead_name=doc.name,
        is_new=doc.is_new(),
        mobile_norm=doc.sr_mobile_norm,
        pending=getattr(doc, "sr_dedupe_pending", None),
        status=getattr(doc, "sr_dedupe_status", None),
        old_group_key=old_key,
    )
