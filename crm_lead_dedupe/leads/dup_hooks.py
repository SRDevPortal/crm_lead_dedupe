import frappe
from crm_lead_dedupe.logging import log_operation
from crm_lead_dedupe.settings import is_enabled
from .dup_utils import (
    DUPLICATE_OF_FIELD,
    LEGACY_DUPLICATE_OF_FIELD,
    DEFAULT_BLOCKED_MOBILES,
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
    filters = {"sr_mobile_norm": doc.sr_mobile_norm}
    if doc.get("sr_lead_pipeline") and frappe.db.has_column(doc.doctype, "sr_lead_pipeline"):
        filters["sr_lead_pipeline"] = doc.get("sr_lead_pipeline")
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


def _mark_pending_group(mobile_norm: str | None):
    if not mobile_norm or not frappe.db.has_column("CRM Lead", "sr_dedupe_pending"):
        return
    frappe.db.sql(
        """
        update `tabCRM Lead`
        set sr_dedupe_pending = 1,
            sr_dedupe_status = 'Pending'
        where sr_mobile_norm = %(mobile_norm)s
        """,
        {"mobile_norm": mobile_norm},
    )


def _mark_doc_pending(doc):
    if not hasattr(doc, "sr_dedupe_pending"):
        return

    if is_valid_auto_merge_mobile(doc.sr_mobile_norm, DEFAULT_BLOCKED_MOBILES):
        doc.sr_dedupe_pending = 1
        if hasattr(doc, "sr_dedupe_status"):
            doc.sr_dedupe_status = "Pending"
        if hasattr(doc, "sr_dedupe_error"):
            doc.sr_dedupe_error = None
    else:
        doc.sr_dedupe_pending = 0
        if hasattr(doc, "sr_dedupe_status"):
            doc.sr_dedupe_status = "Skipped"


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
    Keep Lead saves cheap. The 5-minute scheduler performs duplicate lookup and
    merge by mobile group after the Lead transaction is complete.
    """
    if not is_enabled("hooks"):
        log_operation("lead_before_save.skipped", lead_name=doc.name, reason="hooks_disabled")
        return

    doc.sr_mobile_norm = norm_mobile(doc.mobile_no or "")
    old_key = _store_old_group_key(doc)
    if old_key:
        _mark_pending_group(old_key[0])

    if not getattr(frappe.flags, "crm_lead_dedupe_scheduler", False):
        _mark_doc_pending(doc)

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
