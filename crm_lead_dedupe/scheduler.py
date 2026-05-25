import frappe
from frappe.model.rename_doc import rename_doc
from frappe.utils import cint, now_datetime
from frappe.utils.file_lock import LockTimeoutError
from frappe.utils.synchronization import filelock

from crm_lead_dedupe.integrations.wa_chat_hub import relink_crm_lead_conversations
from crm_lead_dedupe.leads.dup_utils import (
    DT,
    DUPLICATE_OF_FIELD,
    GROUP_STATE_FIELDS,
    LEGACY_DUPLICATE_OF_FIELD,
    _lead_fields,
    is_valid_auto_merge_mobile,
    select_primary_row,
    sync_duplicate_group,
)
from crm_lead_dedupe.logging import log_operation
from crm_lead_dedupe.settings import get_setting, is_enabled


AUTO_MERGE_LOG_DOCTYPE = "CRM Lead Auto Merge Log"
GLOBAL_LOCK = "crm_lead_dedupe_scheduler"
MOBILE_LOCK_PREFIX = "crm_lead_dedupe_mobile_"
HISTORICAL_PROGRESS_KEY = "crm_lead_dedupe_historical_last_mobile_norm"


def _setting_int(key: str, default: int, minimum: int = 1) -> int:
    try:
        value = cint(get_setting(key))
    except Exception:
        value = default
    return max(minimum, value or default)


def _blocked_mobiles() -> set[str]:
    value = get_setting("crm_lead_dedupe_blocked_mobiles") or ""
    if isinstance(value, str):
        return {line.strip() for line in value.splitlines() if line.strip()}
    if isinstance(value, (list, tuple, set)):
        return {str(item).strip() for item in value if str(item).strip()}
    return set()


def _has_required_columns() -> bool:
    required = ("sr_mobile_norm", "sr_dedupe_pending", "sr_dedupe_status")
    return all(frappe.db.has_column(DT, fieldname) for fieldname in required)


def _pending_mobile_groups(limit: int) -> list[str]:
    rows = frappe.db.sql(
        f"""
        select distinct sr_mobile_norm
        from `tab{DT}`
        where sr_dedupe_pending = 1
            and ifnull(sr_mobile_norm, '') != ''
        order by modified asc
        limit %(limit)s
        """,
        {"limit": limit},
        as_dict=True,
    )
    return [row.sr_mobile_norm for row in rows]


@frappe.whitelist()
def queue_historical_duplicate_groups(batch_size: int = 500, reset: bool = False):
    """Mark old duplicate mobile groups pending so the 5-minute scheduler can merge them safely."""
    if not is_enabled("scheduler") or not _has_required_columns():
        return {"queued_groups": 0, "done": True, "skipped": "disabled_or_missing_columns"}

    if reset:
        frappe.defaults.set_global_default(HISTORICAL_PROGRESS_KEY, "")

    batch_size = max(1, cint(batch_size) or 500)
    last_mobile_norm = frappe.defaults.get_global_default(HISTORICAL_PROGRESS_KEY) or ""
    blocked = _blocked_mobiles()
    rows = frappe.db.sql(
        f"""
        select sr_mobile_norm, count(*) as total
        from `tab{DT}`
        where ifnull(sr_mobile_norm, '') != ''
            and sr_mobile_norm > %(last_mobile_norm)s
        group by sr_mobile_norm
        having count(*) > 1
        order by sr_mobile_norm asc
        limit %(batch_size)s
        """,
        {"last_mobile_norm": last_mobile_norm, "batch_size": batch_size},
        as_dict=True,
    )

    if not rows:
        return {"queued_groups": 0, "last_mobile_norm": last_mobile_norm, "done": True}

    queued_groups = 0
    for row in rows:
        mobile_norm = row.sr_mobile_norm
        status = "Pending" if is_valid_auto_merge_mobile(mobile_norm, blocked) else "Skipped"
        pending = 1 if status == "Pending" else 0
        _set_group_status(
            mobile_norm,
            status,
            None if pending else "Unsafe or invalid mobile number",
            pending=pending,
        )
        queued_groups += pending

    last_mobile_norm = rows[-1].sr_mobile_norm
    frappe.defaults.set_global_default(HISTORICAL_PROGRESS_KEY, last_mobile_norm)
    frappe.db.commit()
    return {
        "queued_groups": queued_groups,
        "processed_groups": len(rows),
        "last_mobile_norm": last_mobile_norm,
        "done": len(rows) < batch_size,
    }


def _group_rows(mobile_norm: str):
    return frappe.get_all(
        DT,
        filters={"sr_mobile_norm": mobile_norm},
        fields=_lead_fields(["sr_mobile_norm", *GROUP_STATE_FIELDS]),
        order_by="creation desc",
        limit_page_length=0,
    )


def _set_group_status(mobile_norm: str, status: str, error: str | None = None, pending: int = 0):
    values = {
        "sr_dedupe_pending": pending,
        "sr_dedupe_status": status,
        "sr_dedupe_checked_on": now_datetime(),
    }
    if frappe.db.has_column(DT, "sr_dedupe_error"):
        values["sr_dedupe_error"] = error
    names = frappe.get_all(DT, filters={"sr_mobile_norm": mobile_norm}, pluck="name", limit_page_length=0)
    if names:
        frappe.db.bulk_update(DT, {name: values for name in names}, update_modified=False)


def _write_merge_log(mobile_norm: str, master: str | None, duplicate: str | None, status: str, error: str | None = None):
    log_operation(
        "auto_merge.log",
        mobile_norm=mobile_norm,
        master=master,
        duplicate=duplicate,
        status=status,
        error=error,
    )
    if not frappe.db.exists("DocType", AUTO_MERGE_LOG_DOCTYPE):
        return
    try:
        frappe.get_doc(
            {
                "doctype": AUTO_MERGE_LOG_DOCTYPE,
                "mobile_norm": mobile_norm,
                "master_lead": master,
                "duplicate_lead": duplicate,
                "status": status,
                "error": error,
            }
        ).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "CRM Lead Auto Merge Log Failed")


def _merge_duplicate(master: str, duplicate: str, mobile_norm: str):
    if not frappe.db.exists(DT, master) or not frappe.db.exists(DT, duplicate):
        _write_merge_log(mobile_norm, master, duplicate, "Skipped", "Master or duplicate no longer exists")
        return False

    relink_crm_lead_conversations(master, [duplicate])
    rename_doc(DT, duplicate, master, force=True, merge=True, ignore_permissions=True)

    values = {
        "sr_is_duplicate": 0,
        DUPLICATE_OF_FIELD: None,
        "sr_duplicate_score": 0,
        "sr_dedupe_pending": 0,
        "sr_dedupe_status": "Master",
        "sr_dedupe_checked_on": now_datetime(),
    }
    if frappe.db.has_column(DT, LEGACY_DUPLICATE_OF_FIELD):
        values[LEGACY_DUPLICATE_OF_FIELD] = None
    if frappe.db.has_column(DT, "sr_dedupe_error"):
        values["sr_dedupe_error"] = None
    frappe.db.set_value(DT, master, values, update_modified=False)
    _write_merge_log(mobile_norm, master, duplicate, "Merged")
    return True


def process_mobile_group(mobile_norm: str, max_merges: int, max_group_size: int) -> int:
    blocked = _blocked_mobiles()
    if not is_valid_auto_merge_mobile(mobile_norm, blocked):
        _set_group_status(mobile_norm, "Skipped", "Unsafe or invalid mobile number")
        _write_merge_log(mobile_norm, None, None, "Skipped", "Unsafe or invalid mobile number")
        frappe.db.commit()
        return 0

    lock_name = f"{MOBILE_LOCK_PREFIX}{mobile_norm}"
    with filelock(lock_name, timeout=0):
        rows = _group_rows(mobile_norm)
        if len(rows) <= 1:
            _set_group_status(mobile_norm, "Master")
            frappe.db.commit()
            return 0

        if len(rows) > max_group_size:
            message = f"Group size {len(rows)} exceeds limit {max_group_size}"
            _set_group_status(mobile_norm, "Skipped", message)
            _write_merge_log(mobile_norm, None, None, "Skipped", message)
            frappe.db.commit()
            return 0

        primary = select_primary_row(rows)
        if not primary:
            _set_group_status(mobile_norm, "Skipped", "No primary could be selected")
            frappe.db.commit()
            return 0

        master = primary.name
        merged = 0
        for row in rows:
            if row.name == master:
                continue
            if merged >= max_merges:
                break

            try:
                frappe.flags.crm_lead_dedupe_scheduler = True
                if _merge_duplicate(master, row.name, mobile_norm):
                    merged += 1
                    frappe.db.commit()
            except Exception as exc:
                frappe.db.rollback()
                error = str(exc)[:1000]
                if frappe.db.exists(DT, row.name):
                    values = {
                        "sr_dedupe_pending": 0,
                        "sr_dedupe_status": "Failed",
                        "sr_dedupe_checked_on": now_datetime(),
                    }
                    if frappe.db.has_column(DT, "sr_dedupe_error"):
                        values["sr_dedupe_error"] = error
                    frappe.db.set_value(
                        DT,
                        row.name,
                        values,
                        update_modified=False,
                    )
                    frappe.db.commit()
                _write_merge_log(mobile_norm, master, row.name, "Failed", error)
                frappe.log_error(frappe.get_traceback(), "CRM Lead Auto Merge Failed")
            finally:
                frappe.flags.crm_lead_dedupe_scheduler = False

        try:
            sync_duplicate_group(mobile_norm)
            _set_group_status(mobile_norm, "Master")
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(frappe.get_traceback(), "CRM Lead Group Sync After Auto Merge Failed")

        return merged


def run_auto_merge_scheduler():
    if not is_enabled("scheduler") or not is_enabled("merge"):
        log_operation("auto_merge_scheduler.skipped", reason="disabled")
        return {"processed_groups": 0, "merged": 0, "skipped": "disabled"}

    if not _has_required_columns():
        log_operation("auto_merge_scheduler.skipped", reason="missing_columns")
        return {"processed_groups": 0, "merged": 0, "skipped": "missing_columns"}

    max_pending = _setting_int("crm_lead_dedupe_max_pending_leads", 2000)
    max_groups = _setting_int("crm_lead_dedupe_max_mobile_groups", 500)
    max_merges = _setting_int("crm_lead_dedupe_max_merges_per_run", 100)
    max_group_size = _setting_int("crm_lead_dedupe_max_group_size", 100)
    limit = min(max_pending, max_groups)

    try:
        with filelock(GLOBAL_LOCK, timeout=0):
            mobile_groups = _pending_mobile_groups(limit)
            processed_groups = 0
            merged = 0

            log_operation("auto_merge_scheduler.start", group_count=len(mobile_groups), max_merges=max_merges)
            for mobile_norm in mobile_groups:
                if merged >= max_merges:
                    break
                try:
                    merged += process_mobile_group(mobile_norm, max_merges - merged, max_group_size)
                    processed_groups += 1
                except LockTimeoutError:
                    log_operation("auto_merge_scheduler.group_locked", mobile_norm=mobile_norm)
                except Exception:
                    frappe.db.rollback()
                    _set_group_status(mobile_norm, "Failed", frappe.get_traceback()[:1000])
                    frappe.db.commit()
                    frappe.log_error(frappe.get_traceback(), "CRM Lead Auto Merge Group Failed")

            result = {"processed_groups": processed_groups, "merged": merged}
            log_operation("auto_merge_scheduler.done", **result)
            return result
    except LockTimeoutError:
        log_operation("auto_merge_scheduler.skipped", reason="already_running")
        return {"processed_groups": 0, "merged": 0, "skipped": "already_running"}
